from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from threading import Lock

from fastapi import Depends
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.ai import LLMClient
from backend.app.ai.models import DiagnosticQuestionDraft
from backend.app.ai.references import normalize_source_reference
from backend.app.core.settings import Settings, get_settings
from backend.app.db.models import Course, CourseKnowledgeBuildState, KnowledgeNode, Question
from backend.app.db.session import get_db
from backend.app.models import (
    KnowledgeDifficulty,
    KnowledgeRelationRole,
    QuestionDifficulty,
    QuestionType,
    QuestionValidationStatus,
)
from backend.app.repositories import QuestionRepository, UserRepository
from backend.app.schemas.question_generation import (
    CourseQuestionPreparationFailureSchema,
    CourseQuestionPreparationResponseSchema,
    DiagnosticQuestionGenerationResponseSchema,
    QuestionBankItemSchema,
    QuestionBankListSchema,
    QuestionBankNodeSchema,
    QuestionBankReadinessSchema,
    QuestionReviewResponseSchema,
)
from backend.app.services.assessment_assembly_service import AssessmentAssemblyService
from backend.app.services.diagnostic_domain_service import DiagnosticDomainError, DiagnosticDomainService
from backend.app.services.diagnostic_question_generation import (
    DiagnosticQuestionGenerationError,
    DiagnosticQuestionGenerationService,
)

_generation_locks_guard = Lock()
_course_generation_locks: dict[int, Lock] = {}


class DiagnosticQuestionBankError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class DiagnosticQuestionBankService:
    """Application boundary for reviewed diagnostic-question publication."""

    _DIFFICULTY_MAP = {
        KnowledgeDifficulty.BASIC: QuestionDifficulty.EASY,
        KnowledgeDifficulty.INTERMEDIATE: QuestionDifficulty.MEDIUM,
        KnowledgeDifficulty.ADVANCED: QuestionDifficulty.HARD,
    }
    COURSE_PREPARATION_BATCH_LIMIT = 4
    _QUESTION_TYPE_ORDER = (
        QuestionType.SINGLE_CHOICE,
        QuestionType.TRUE_FALSE,
        QuestionType.MULTIPLE_CHOICE,
    )
    _QUESTION_DIFFICULTY_ORDER = (
        QuestionDifficulty.MEDIUM,
        QuestionDifficulty.EASY,
        QuestionDifficulty.HARD,
    )

    def __init__(
        self,
        session: Session,
        settings: Settings,
        llm_client_factory: Callable[[Settings], LLMClient] | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.llm_client_factory = llm_client_factory
        self.questions = QuestionRepository(session)
        self.users = UserRepository(session)

    def readiness(self, course_id: int) -> QuestionBankReadinessSchema:
        owner_id = self._owner_id()
        preview = AssessmentAssemblyService(self.session).preview_question_bank(owner_id, course_id)
        with self.session.begin():
            questions = self.questions.list_for_course_owner(course_id, owner_id)
            status_counts = Counter(question.validation_status for question in questions)
            required_nodes = [
                QuestionBankNodeSchema(
                    knowledge_node_id=node.id,
                    knowledge_node_name=node.name,
                    has_validated_question=self._node_has_status(
                        questions, node.id, QuestionValidationStatus.VALIDATED
                    ),
                    has_pending_question=self._node_has_status(questions, node.id, QuestionValidationStatus.PENDING),
                )
                for node in preview.required_nodes
            ]
        readiness = preview.readiness
        return QuestionBankReadinessSchema(
            course_id=course_id,
            validated_count=status_counts[QuestionValidationStatus.VALIDATED],
            pending_count=status_counts[QuestionValidationStatus.PENDING],
            rejected_count=status_counts[QuestionValidationStatus.REJECTED],
            covered_core_nodes=readiness.covered_knowledge_nodes,
            total_core_nodes=readiness.eligible_knowledge_nodes,
            minimum_required=AssessmentAssemblyService.MIN_QUESTIONS,
            required_questions=readiness.required_questions,
            can_start=readiness.can_start,
            reason_code=readiness.reason_code,
            required_nodes=required_nodes,
        )

    def list_questions(
        self,
        course_id: int,
        status: QuestionValidationStatus | None = None,
    ) -> QuestionBankListSchema:
        owner_id = self._owner_id()
        with self.session.begin():
            self._require_owned_course(owner_id, course_id)
            questions = self.questions.list_for_course_owner(course_id, owner_id, status)
            items = [self._item(question) for question in questions]
        return QuestionBankListSchema(count=len(items), questions=items)

    def generate_pending(
        self,
        *,
        course_id: int,
        knowledge_node_id: int,
    ) -> DiagnosticQuestionGenerationResponseSchema:
        owner_id = self._owner_id()
        lock = self._course_generation_lock(course_id)
        with lock:
            with self.session.begin():
                self._require_owned_course(owner_id, course_id)
                node = self.session.scalar(
                    select(KnowledgeNode).where(
                        KnowledgeNode.id == knowledge_node_id,
                        KnowledgeNode.course_id == course_id,
                        KnowledgeNode.is_active.is_(True),
                    )
                )
                if node is None:
                    raise DiagnosticQuestionBankError(
                        "KNOWLEDGE_NODE_NOT_FOUND", "Knowledge node was not found in this course."
                    )
                existing = self.questions.list_for_primary_node(course_id, knowledge_node_id)
                if any(item.validation_status == QuestionValidationStatus.PENDING for item in existing):
                    raise DiagnosticQuestionBankError(
                        "QUESTION_INVALID_STATE", "A pending question for this knowledge node already requires review."
                    )
                if any(item.validation_status == QuestionValidationStatus.VALIDATED for item in existing):
                    raise DiagnosticQuestionBankError(
                        "QUESTION_INVALID_STATE", "This knowledge node is already covered by a validated question."
                    )
                difficulty = self._DIFFICULTY_MAP[node.difficulty]

            generator = self._generator()
            result = generator.generate_questions_for_node(
                owner_id=owner_id,
                course_id=course_id,
                knowledge_node_id=knowledge_node_id,
                question_type=QuestionType.SINGLE_CHOICE,
                difficulty=difficulty,
                count=1,
                initial_status=QuestionValidationStatus.PENDING,
            )
            with self.session.begin():
                items = [
                    self._item(self._require_question(owner_id, course_id, question.id))
                    for question in result.questions
                ]
            return DiagnosticQuestionGenerationResponseSchema(
                provider=result.provider,
                model=result.model,
                prompt_version=result.prompt_version,
                requested_count=result.requested_count,
                accepted_count=result.accepted_count,
                questions=items,
            )

    def prepare_course(self, course_id: int) -> CourseQuestionPreparationResponseSchema:
        """Prepare one bounded, deterministic batch for the current assembly requirements."""
        owner_id = self._owner_id()
        lock = self._course_generation_lock(course_id)
        with lock:
            preview = AssessmentAssemblyService(self.session).preview_question_bank(owner_id, course_id)
            if not preview.required_nodes and not preview.readiness.can_start:
                raise DiagnosticQuestionBankError(
                    "KNOWLEDGE_MODEL_NOT_READY",
                    "The course has no active knowledge nodes available for diagnostic preparation.",
                )

            with self.session.begin():
                self._require_owned_course(owner_id, course_id)
                existing = self.questions.list_for_course_owner(course_id, owner_id)
                planned_nodes = [
                    (node.id, node.name)
                    for node in preview.required_nodes
                    if not self._node_has_status(existing, node.id, QuestionValidationStatus.VALIDATED)
                    and not self._node_has_status(existing, node.id, QuestionValidationStatus.PENDING)
                ][: self.COURSE_PREPARATION_BATCH_LIMIT]
                type_counts = Counter(question.question_type for question in existing)
                difficulty_counts = Counter(question.difficulty for question in existing)

            generated: list[QuestionBankItemSchema] = []
            failures: list[CourseQuestionPreparationFailureSchema] = []
            generator = self._generator()
            for node_id, node_name in planned_nodes:
                question_type = min(
                    self._QUESTION_TYPE_ORDER,
                    key=lambda value: (type_counts[value], self._QUESTION_TYPE_ORDER.index(value)),
                )
                difficulty = min(
                    self._QUESTION_DIFFICULTY_ORDER,
                    key=lambda value: (
                        difficulty_counts[value],
                        self._QUESTION_DIFFICULTY_ORDER.index(value),
                    ),
                )
                try:
                    result = generator.generate_questions_for_node(
                        owner_id=owner_id,
                        course_id=course_id,
                        knowledge_node_id=node_id,
                        question_type=question_type,
                        difficulty=difficulty,
                        count=1,
                        initial_status=QuestionValidationStatus.PENDING,
                    )
                    with self.session.begin():
                        items = [
                            self._item(self._require_question(owner_id, course_id, question.id))
                            for question in result.questions
                        ]
                    generated.extend(items)
                    type_counts[question_type] += len(items)
                    difficulty_counts[difficulty] += len(items)
                except DiagnosticQuestionGenerationError as error:
                    failures.append(
                        CourseQuestionPreparationFailureSchema(
                            knowledge_node_id=node_id,
                            knowledge_node_name=node_name,
                            code=error.code,
                            message=error.message,
                        )
                    )

            with self.session.begin():
                pending_count = len(
                    self.questions.list_for_course_owner(
                        course_id,
                        owner_id,
                        QuestionValidationStatus.PENDING,
                    )
                )
            return CourseQuestionPreparationResponseSchema(
                course_id=course_id,
                planned_count=len(planned_nodes),
                generated_count=len(generated),
                failed_count=len(failures),
                pending_review_count=pending_count,
                questions=generated,
                failures=failures,
            )

    def approve(self, course_id: int, question_id: int) -> QuestionReviewResponseSchema:
        owner_id = self._owner_id()
        with self.session.begin():
            self._require_owned_course(owner_id, course_id)
            question = self._require_question(owner_id, course_id, question_id)
            self._require_pending(question)
            self._validate_for_publication(owner_id, course_id, question)
            changed = self.questions.transition_status(
                question_id=question.id,
                course_id=course_id,
                expected=QuestionValidationStatus.PENDING,
                target=QuestionValidationStatus.VALIDATED,
            )
            if not changed:
                raise DiagnosticQuestionBankError("QUESTION_INVALID_STATE", "Question state changed before approval.")
            self.session.refresh(question)
            item = self._item(question)
        return QuestionReviewResponseSchema(question=item)

    def reject(self, course_id: int, question_id: int) -> QuestionReviewResponseSchema:
        owner_id = self._owner_id()
        with self.session.begin():
            self._require_owned_course(owner_id, course_id)
            question = self._require_question(owner_id, course_id, question_id)
            self._require_pending(question)
            changed = self.questions.transition_status(
                question_id=question.id,
                course_id=course_id,
                expected=QuestionValidationStatus.PENDING,
                target=QuestionValidationStatus.REJECTED,
            )
            if not changed:
                raise DiagnosticQuestionBankError("QUESTION_INVALID_STATE", "Question state changed before rejection.")
            self.session.refresh(question)
            item = self._item(question)
        return QuestionReviewResponseSchema(question=item)

    def _validate_for_publication(self, owner_id: int, course_id: int, question: Question) -> None:
        state = self.session.get(CourseKnowledgeBuildState, course_id)
        if state is None or state.status != "success":
            raise DiagnosticQuestionBankError(
                "KNOWLEDGE_MODEL_NOT_READY", "The course knowledge model is not ready for question review."
            )
        primary_links = [
            link
            for link in question.knowledge_links
            if link.relation_role == KnowledgeRelationRole.PRIMARY
            and link.course_id == course_id
            and link.knowledge_node is not None
            and link.knowledge_node.course_id == course_id
            and link.knowledge_node.is_active
        ]
        if len(primary_links) != 1:
            raise DiagnosticQuestionBankError(
                "QUESTION_ALIGNMENT_INVALID",
                "Question must have exactly one active primary knowledge node in this course.",
            )
        primary_node = primary_links[0].knowledge_node
        try:
            snapshot = DiagnosticDomainService.build_question_snapshot(question)
        except DiagnosticDomainError as error:
            raise DiagnosticQuestionBankError("QUESTION_QUALITY_INVALID", error.message) from error

        generator = self._generator()
        verified_sources = generator.verified_sources_for_node(primary_node.id, course_id)
        allowed_sources = {
            (source.material_id, normalize_source_reference(source.source_reference)): source
            for source in verified_sources
        }
        if not snapshot.source_refs:
            raise DiagnosticQuestionBankError("QUESTION_SOURCE_INVALID", "Question has no verified source references.")
        for source_ref in snapshot.source_refs:
            if source_ref.material_id is None:
                raise DiagnosticQuestionBankError(
                    "QUESTION_SOURCE_INVALID", "Question source must reference a course material."
                )
            source = allowed_sources.get(
                (source_ref.material_id, normalize_source_reference(source_ref.source_reference))
            )
            if source is None:
                raise DiagnosticQuestionBankError(
                    "QUESTION_SOURCE_INVALID", "Question source is no longer valid for its primary knowledge node."
                )
            if source_ref.excerpt and source.excerpt[: len(source_ref.excerpt)] != source_ref.excerpt:
                raise DiagnosticQuestionBankError(
                    "QUESTION_SOURCE_INVALID", "Question source content changed after generation."
                )

        try:
            draft = DiagnosticQuestionDraft.model_validate(
                {
                    "question_type": snapshot.question_type,
                    "stem": snapshot.stem,
                    "options": [option.model_dump(mode="json") for option in snapshot.options],
                    "correct_answer": snapshot.correct_answer,
                    "explanation": snapshot.explanation,
                    "difficulty": snapshot.difficulty,
                    "knowledge_node_ids": [primary_node.id],
                    "source_refs": [
                        {
                            "material_id": source.material_id,
                            "source_reference": source.source_reference,
                        }
                        for source in snapshot.source_refs
                    ],
                }
            )
            generator.quality.validate_basic_quality(draft)
        except (ValidationError, ValueError) as error:
            raise DiagnosticQuestionBankError(
                "QUESTION_QUALITY_INVALID", "Question failed deterministic quality validation."
            ) from error

        validated = [
            item
            for item in self.questions.list_for_course_owner(course_id, owner_id, QuestionValidationStatus.VALIDATED)
            if item.id != question.id
        ]
        primary_stems = [
            item.stem
            for item in validated
            if any(
                link.relation_role == KnowledgeRelationRole.PRIMARY and link.knowledge_node_id == primary_node.id
                for link in item.knowledge_links
            )
        ]
        duplicate = generator.quality.detect_duplicate(
            stem=question.stem,
            course_stems=[item.stem for item in validated],
            primary_node_stems=primary_stems,
            accepted_stems=[],
        )
        if duplicate.duplicate:
            raise DiagnosticQuestionBankError(
                "QUESTION_DUPLICATE", duplicate.reason or "Question duplicates a validated item."
            )

    def _generator(self) -> DiagnosticQuestionGenerationService:
        if self.llm_client_factory is None:
            return DiagnosticQuestionGenerationService(self.session, self.settings)
        return DiagnosticQuestionGenerationService(self.session, self.settings, self.llm_client_factory)

    def _owner_id(self) -> int:
        with self.session.begin():
            owner = self.users.get_by_email(self.settings.legacy_bootstrap_user)
            if owner is None:
                raise DiagnosticQuestionBankError("COURSE_NOT_FOUND", "Course not found.")
            return owner.id

    def _require_owned_course(self, owner_id: int, course_id: int) -> Course:
        course = self.session.scalar(select(Course).where(Course.id == course_id, Course.owner_id == owner_id))
        if course is None:
            raise DiagnosticQuestionBankError("COURSE_NOT_FOUND", "Course not found.")
        return course

    def _require_question(self, owner_id: int, course_id: int, question_id: int) -> Question:
        question = self.questions.get_for_owner(question_id, owner_id)
        if question is None or question.course_id != course_id:
            raise DiagnosticQuestionBankError("QUESTION_NOT_FOUND", "Question not found.")
        return question

    @staticmethod
    def _require_pending(question: Question) -> None:
        if question.validation_status != QuestionValidationStatus.PENDING:
            raise DiagnosticQuestionBankError(
                "QUESTION_INVALID_STATE",
                f"Question must be pending; current state is {question.validation_status.value}.",
            )

    @staticmethod
    def _node_has_status(
        questions: list[Question],
        node_id: int,
        status: QuestionValidationStatus,
    ) -> bool:
        return any(
            question.validation_status == status
            and any(
                link.relation_role == KnowledgeRelationRole.PRIMARY and link.knowledge_node_id == node_id
                for link in question.knowledge_links
            )
            for question in questions
        )

    @staticmethod
    def _item(question: Question) -> QuestionBankItemSchema:
        primary_links = [
            link
            for link in question.knowledge_links
            if link.relation_role == KnowledgeRelationRole.PRIMARY and link.knowledge_node is not None
        ]
        primary = primary_links[0].knowledge_node if len(primary_links) == 1 else None
        return QuestionBankItemSchema(
            question_id=question.id,
            course_id=question.course_id,
            knowledge_node_id=primary.id if primary is not None else None,
            knowledge_node_name=primary.name if primary is not None else None,
            question_type=question.question_type,
            difficulty=question.difficulty,
            stem=question.stem,
            options=question.options,
            correct_answer=question.correct_answer,
            explanation=question.explanation,
            source_refs=question.source_refs,
            validation_status=question.validation_status,
            created_at=question.created_at,
        )

    @staticmethod
    def _course_generation_lock(course_id: int) -> Lock:
        with _generation_locks_guard:
            return _course_generation_locks.setdefault(course_id, Lock())


def get_diagnostic_question_bank_service(
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DiagnosticQuestionBankService:
    return DiagnosticQuestionBankService(session, settings)


__all__ = [
    "DiagnosticQuestionBankError",
    "DiagnosticQuestionBankService",
    "get_diagnostic_question_bank_service",
]
