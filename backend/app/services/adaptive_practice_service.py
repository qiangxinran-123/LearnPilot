from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from fastapi import Depends
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from backend.app.core.settings import Settings, get_settings
from backend.app.db.models import Assessment, AssessmentQuestion, LearningSession, LearningSessionTaskState, Response
from backend.app.db.session import get_db
from backend.app.models import (
    AssessmentStatus,
    AssessmentType,
    ConfidenceLevel,
    KnowledgeDifficulty,
    LearningSessionStatus,
    LearningSessionTaskPhase,
    LearningSessionTaskStatus,
    MasteryStatus,
    QuestionDifficulty,
    QuestionType,
    QuestionValidationStatus,
)
from backend.app.repositories import (
    AssessmentRepository,
    LearningEvidenceRepository,
    LearningSessionRepository,
    QuestionRepository,
    ResponseRepository,
    StudentKnowledgeStateRepository,
    UserRepository,
)
from backend.app.schemas.diagnostic import AssessmentQuestionSnapshotSchema
from backend.app.schemas.mastery_api import KnowledgeNodeMasteryReadSchema, KnowledgeStateAvailability
from backend.app.schemas.practice import (
    PracticeAnswerCreate,
    PracticeAttemptRead,
    PracticeQuestionRead,
    PracticeRead,
    PracticeSummaryRead,
)
from backend.app.services.deterministic_objective_scorer import (
    DeterministicObjectiveScorer,
    DeterministicScoringError,
)
from backend.app.services.diagnostic_domain_service import DiagnosticDomainError, DiagnosticDomainService
from backend.app.services.diagnostic_evidence_ingestion import DiagnosticEvidenceExtractor
from backend.app.services.diagnostic_question_generation import (
    DiagnosticQuestionGenerationError,
    DiagnosticQuestionGenerationService,
)
from backend.app.services.diagnostic_question_quality import normalize_question_stem
from backend.app.services.learning_evidence_service import LearningEvidenceService
from backend.app.services.learning_session_service import LearningSessionError
from backend.app.services.learning_settlement_service import LearningSettlementService
from backend.app.services.mastery_config import MASTERY_V1_CONFIG
from backend.app.services.mastery_read_service import MasteryReadService, is_persisted_mastery_state_current
from backend.app.services.mastery_service import MasteryService

MAX_PRACTICE_QUESTIONS = 5
logger = logging.getLogger(__name__)
DIFFICULTY_ORDER = (
    QuestionDifficulty.EASY,
    QuestionDifficulty.MEDIUM,
    QuestionDifficulty.HARD,
)
DIFFICULTY_FALLBACK = {
    QuestionDifficulty.EASY: DIFFICULTY_ORDER,
    QuestionDifficulty.MEDIUM: (
        QuestionDifficulty.MEDIUM,
        QuestionDifficulty.EASY,
        QuestionDifficulty.HARD,
    ),
    QuestionDifficulty.HARD: tuple(reversed(DIFFICULTY_ORDER)),
}
SUPPORTED_TYPES = {
    QuestionType.SINGLE_CHOICE,
    QuestionType.MULTIPLE_CHOICE,
    QuestionType.TRUE_FALSE,
}


class AdaptivePracticeError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class AdaptivePracticeService:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        *,
        question_generator: DiagnosticQuestionGenerationService | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.sessions = LearningSessionRepository(session)
        self.assessments = AssessmentRepository(session)
        self.questions = QuestionRepository(session)
        self.responses = ResponseRepository(session)
        self.users = UserRepository(session)
        self.scorer = DeterministicObjectiveScorer()
        self.question_generator = question_generator or DiagnosticQuestionGenerationService(
            session, settings.model_copy(update={"llm_max_attempts": 1})
        )

    def start_or_next_for_configured_user(self, session_id: int) -> PracticeRead:
        user_id, course_id, node_id, needs_initial = self._preflight(session_id)
        request_id = uuid4().hex
        mastery = None
        if needs_initial:
            mastery = MasteryReadService(self.session, self.settings).node_mastery(course_id, node_id)
        result = self._next_from_bank(session_id, user_id, mastery)
        if result.status == "question_bank_empty":
            error_code = None
            generated_count: int | str = "unknown"
            checked_count = 0
            duplicate_count = 0
            # The bank transaction has committed. The generator manages its own
            # source reads and persistence without holding a write during inference.
            try:
                batch = self.question_generator.generate_questions_for_node(
                    owner_id=user_id,
                    course_id=course_id,
                    knowledge_node_id=node_id,
                    question_type=QuestionType.SINGLE_CHOICE,
                    difficulty=result.current_difficulty,
                    count=1,
                    initial_status=QuestionValidationStatus.PENDING,
                    practice_only=True,
                )
                generated_count = batch.accepted_count + batch.rejected_count
                checked_count = batch.accepted_count
                duplicate_count = batch.rejected_count
                logger.info(
                    "practice_replenishment request_id=%s course_id=%s session_id=%s node_id=%s provider_mode=%s "
                    "generated=%s accepted=%s rejected=%s",
                    request_id,
                    course_id,
                    session_id,
                    node_id,
                    self.settings.llm_mode,
                    batch.requested_count,
                    batch.accepted_count,
                    batch.rejected_count,
                )
            except DiagnosticQuestionGenerationError as error:
                # The generator logs the failure. Recheck in case a concurrent
                # request filled the bank while this one was waiting.
                error_code = error.code
                if error.code == "QUESTION_DUPLICATE":
                    generated_count = 1
                    duplicate_count = 1
            except Exception as error:
                self.session.rollback()
                logger.error("Practice question generation failed: %s", type(error).__name__)
                error_code = "QUESTION_GENERATION_FAILED"
            result = self._next_from_bank(session_id, user_id, mastery)
            if result.status == "question_bank_empty":
                result.generation_error = error_code or "QUESTION_UNAVAILABLE"
                with self.session.begin():
                    task = self._practice_task(self._require_owned(session_id, user_id, for_update=True))
                    task.progress = {**task.progress, "generation_error": result.generation_error}
            logger.info(
                "practice_replenishment_result request_id=%s course_id=%s session_id=%s node_id=%s "
                "provider_mode=%s triggered=true generated=%s checked=%s duplicate_filtered=%s error=%s "
                "status=%s available=%s",
                request_id,
                course_id,
                session_id,
                node_id,
                self.settings.llm_mode,
                generated_count,
                checked_count,
                duplicate_count,
                error_code or "none",
                result.status,
                int(result.current_question is not None),
            )
        return self._settle_if_mastered(result)

    def read_for_configured_user(self, session_id: int) -> PracticeRead:
        """Restore an existing practice without requesting or creating questions."""
        with self.session.begin():
            user_id = self._owner_id()
            learning_session = self._require_owned(session_id, user_id)
            assessment = self._practice_assessment(learning_session, user_id)
            if assessment is None:
                raise AdaptivePracticeError("PRACTICE_NOT_STARTED", "Practice has not started.")
            task = self._practice_task(learning_session)
            result = self._read(learning_session, assessment, task, reused=True)
            if result.status == "question_bank_empty":
                result.generation_error = task.progress.get("generation_error")
            return result

    def finish_for_configured_user(self, session_id: int) -> PracticeRead:
        with self.session.begin():
            user_id = self._owner_id()
            learning_session = self._require_owned(session_id, user_id, for_update=True)
            assessment = self._practice_assessment(learning_session, user_id, for_update=True)
            task = self._practice_task(learning_session)
            if assessment is None:
                raise AdaptivePracticeError("PRACTICE_NOT_STARTED", "Practice has not started.")
            if assessment.status != AssessmentStatus.SUBMITTED:
                self._require_practice_ready(learning_session)
                if not _submitted_pairs(assessment) or _current_unanswered(assessment) is not None:
                    raise AdaptivePracticeError("PRACTICE_NOT_READY", "Complete a question before ending practice.")
                if not task.progress.get("bank_exhausted"):
                    raise AdaptivePracticeError("PRACTICE_NOT_READY", "Practice questions are still available.")
                self._complete_practice(assessment, task, reason="no_questions")
            result = self._read(learning_session, assessment, task)
        try:
            LearningSettlementService(self.session, self.settings).complete_for_configured_user(session_id)
        except LearningSessionError as error:
            raise AdaptivePracticeError(error.code, error.message) from error
        return result

    def _next_from_bank(
        self, session_id: int, user_id: int, mastery: KnowledgeNodeMasteryReadSchema | None
    ) -> PracticeRead:
        try:
            with self.session.begin():
                learning_session = self._require_owned(session_id, user_id, for_update=True)
                assessment = self._practice_assessment(learning_session, user_id, for_update=True)
                if learning_session.status == LearningSessionStatus.COMPLETED and assessment is not None:
                    return self._read(learning_session, assessment, self._practice_task(learning_session), reused=True)
                task = self._require_practice_ready(learning_session)
                if assessment is None:
                    assessment = self.assessments.create(
                        Assessment(
                            course_id=learning_session.course_id,
                            owner_id=user_id,
                            assessment_type=AssessmentType.PRACTICE,
                            status=AssessmentStatus.IN_PROGRESS,
                            started_at=datetime.now(timezone.utc),
                        )
                    )
                    learning_session.practice_assessment_id = assessment.id
                    self._start_task(learning_session, task)
                    target = {
                        KnowledgeDifficulty.BASIC: self.settings.practice_basic_target,
                        KnowledgeDifficulty.INTERMEDIATE: self.settings.practice_intermediate_target,
                        KnowledgeDifficulty.ADVANCED: self.settings.practice_advanced_target,
                    }.get(learning_session.target_knowledge_node.difficulty, self.settings.practice_intermediate_target)
                    task.progress = {**task.progress, "max_questions": target}
                    desired = _initial_difficulty(mastery)
                    self._set_progress(task, desired, answered_count=0, bank_exhausted=False)
                else:
                    desired = _stored_difficulty(task)

                if assessment.status == AssessmentStatus.SUBMITTED:
                    return self._read(learning_session, assessment, task, reused=True)
                current = _current_unanswered(assessment)
                if current is not None:
                    return self._read(learning_session, assessment, task, reused=True)

                attempts = _submitted_pairs(assessment)
                if len(attempts) >= _question_target(task):
                    self._complete_practice(assessment, task)
                    return self._read(learning_session, assessment, task)
                if attempts:
                    desired = _next_difficulty(attempts)

                selected = self._select_question(
                    owner_id=user_id,
                    course_id=learning_session.course_id,
                    node_id=learning_session.target_knowledge_node_id,
                    desired=desired,
                    excluded={item.question_id for item in assessment.questions if item.question_id is not None},
                )
                if selected is None:
                    self._set_progress(
                        task,
                        desired,
                        answered_count=len(attempts),
                        bank_exhausted=True,
                    )
                    return self._read(learning_session, assessment, task)

                snapshot = DiagnosticDomainService.build_question_snapshot(selected).model_dump(mode="json")
                if selected.validation_status == QuestionValidationStatus.PENDING:
                    snapshot["auto_checked"] = True
                self.assessments.add_question_snapshot(
                    AssessmentQuestion(
                        assessment=assessment,
                        question_id=selected.id,
                        order_index=len(assessment.questions),
                        question_snapshot=snapshot,
                    )
                )
                self._set_progress(
                    task,
                    selected.difficulty,
                    answered_count=len(attempts),
                    bank_exhausted=False,
                )
                self.session.flush()
                return self._read(learning_session, assessment, task)
        except DiagnosticDomainError as error:
            raise AdaptivePracticeError(error.code, error.message) from error
        except IntegrityError as error:
            self.session.rollback()
            return self._read_after_conflict(session_id, user_id, error)
        except OperationalError as error:
            raise AdaptivePracticeError(
                "PRACTICE_STATE_CONFLICT", "Practice changed concurrently; retry the request."
            ) from error

    def answer_for_configured_user(
        self,
        *,
        session_id: int,
        assessment_question_id: int,
        payload: PracticeAnswerCreate,
    ) -> PracticeRead:
        result = self._record_answer(
            session_id=session_id, assessment_question_id=assessment_question_id, payload=payload
        )
        return self._settle_if_mastered(result)

    def _settle_if_mastered(self, result: PracticeRead) -> PracticeRead:
        if result.completion_reason == "mastered":
            try:
                LearningSettlementService(self.session, self.settings).complete_for_configured_user(result.session_id)
            except LearningSessionError as error:
                raise AdaptivePracticeError(error.code, error.message) from error
        return result

    def _record_answer(
        self,
        *,
        session_id: int,
        assessment_question_id: int,
        payload: PracticeAnswerCreate,
    ) -> PracticeRead:
        if not payload.selected_options:
            raise AdaptivePracticeError("ANSWER_REQUIRED", "Select at least one answer before submitting.")
        try:
            with self.session.begin():
                user_id = self._owner_id()
                learning_session = self._require_owned(session_id, user_id, for_update=True)
                session_completed = learning_session.status == LearningSessionStatus.COMPLETED
                task = (
                    self._practice_task(learning_session)
                    if session_completed
                    else self._require_practice_ready(learning_session)
                )
                assessment = self._practice_assessment(learning_session, user_id, for_update=True)
                if assessment is None:
                    raise AdaptivePracticeError("PRACTICE_NOT_STARTED", "Practice has not started.")
                question = next(
                    (item for item in assessment.questions if item.id == assessment_question_id),
                    None,
                )
                if question is None:
                    raise AdaptivePracticeError("PRACTICE_QUESTION_NOT_FOUND", "Practice question not found.")
                existing = question.response
                answer_payload = payload.model_dump(mode="json")
                if existing is not None:
                    if existing.answer_payload != answer_payload:
                        raise AdaptivePracticeError(
                            "PRACTICE_RESPONSE_LOCKED",
                            "A submitted practice answer cannot be changed.",
                        )
                    return self._read(learning_session, assessment, task, reused=True)
                if session_completed or assessment.status != AssessmentStatus.IN_PROGRESS:
                    raise AdaptivePracticeError("PRACTICE_COMPLETED", "Practice is already complete.")
                current = _current_unanswered(assessment)
                if current is None or current.id != question.id:
                    raise AdaptivePracticeError(
                        "PRACTICE_QUESTION_STALE",
                        "This is no longer the current practice question.",
                    )

                try:
                    score = self.scorer.score(question.question_snapshot, payload)
                except DeterministicScoringError as error:
                    raise AdaptivePracticeError(error.code, error.message) from error
                now = datetime.now(timezone.utc)
                if "mastery_before" not in task.progress:
                    prior = StudentKnowledgeStateRepository(self.session).get(
                        user_id=user_id,
                        course_id=learning_session.course_id,
                        knowledge_node_id=learning_session.target_knowledge_node_id,
                    )
                    rows = LearningEvidenceRepository(self.session).list_for_current_node(
                        user_id=user_id,
                        course_id=learning_session.course_id,
                        knowledge_node_id=learning_session.target_knowledge_node_id,
                    )
                    before = (
                        float(prior.mastery_score)
                        if prior is not None
                        and prior.mastery_score is not None
                        and is_persisted_mastery_state_current(
                            node_id=learning_session.target_knowledge_node_id, state=prior, rows=rows
                        )
                        else None
                    )
                    task.progress = {**task.progress, "mastery_before": "" if before is None else str(before)}
                response = self.responses.create_submitted(
                    Response(
                        assessment_id=assessment.id,
                        assessment_question_id=question.id,
                        answer_payload=answer_payload,
                        answered_at=now,
                        submitted_at=now,
                        is_correct=score.is_correct,
                        points_awarded=score.points_awarded,
                    )
                )
                question.response = response
                self.session.flush()
                plan = DiagnosticEvidenceExtractor(self.session).extract_assessment(
                    assessment.id,
                    expected_user_id=user_id,
                    expected_course_id=learning_session.course_id,
                    in_transaction=True,
                )
                if plan.issues:
                    raise AdaptivePracticeError("PRACTICE_EVIDENCE_INVALID", "Practice evidence could not be recorded.")
                evidence = LearningEvidenceRepository(self.session)
                mastered = False
                for candidate in plan.candidates:
                    if candidate.source_response_id != response.id:
                        continue
                    snapshot = AssessmentQuestionSnapshotSchema.model_validate(question.question_snapshot)
                    if evidence.has_similar_question_evidence(
                        user_id=user_id,
                        course_id=learning_session.course_id,
                        node_id=candidate.historical_knowledge_node_ref,
                        snapshot=question.question_snapshot,
                    ) or evidence.has_source_question_evidence(
                        user_id=user_id,
                        course_id=learning_session.course_id,
                        source_question_id=snapshot.source_question_id,
                        source_question_version=snapshot.source_question_version,
                        historical_knowledge_node_ref=candidate.historical_knowledge_node_ref,
                    ):
                        continue
                    LearningEvidenceService(self.session).create(candidate, in_transaction=True)
                    if candidate.current_knowledge_node_id is not None:
                        state = (
                            MasteryService(self.session)
                            .refresh_state(
                                user_id=user_id,
                                course_id=learning_session.course_id,
                                knowledge_node_id=candidate.current_knowledge_node_id,
                                in_transaction=True,
                            )
                            .state
                        )
                        if state.knowledge_node_id == learning_session.target_knowledge_node_id:
                            mastered = (
                                state.mastery_status == MasteryStatus.GOOD_PERFORMANCE
                                and state.confidence_level in {ConfidenceLevel.MEDIUM, ConfidenceLevel.HIGH}
                                and state.independent_evidence_count >= MASTERY_V1_CONFIG.minimum_independent_evidence
                            )
                attempts = _submitted_pairs(assessment)
                desired = _next_difficulty(attempts)
                self._set_progress(
                    task,
                    desired,
                    answered_count=len(attempts),
                    bank_exhausted=False,
                )
                if mastered or len(attempts) >= _question_target(task):
                    self._complete_practice(assessment, task, mastered=mastered)
                self.session.flush()
                return self._read(learning_session, assessment, task)
        except IntegrityError as error:
            self.session.rollback()
            return self._replay_answer(session_id, assessment_question_id, payload, error)
        except OperationalError as error:
            self.session.rollback()
            raise AdaptivePracticeError(
                "PRACTICE_STATE_CONFLICT",
                "Practice changed concurrently; retry the request.",
            ) from error

    def _preflight(self, session_id: int) -> tuple[int, int, int, bool]:
        with self.session.begin():
            user_id = self._owner_id()
            learning_session = self._require_owned(session_id, user_id)
            return (
                user_id,
                learning_session.course_id,
                learning_session.target_knowledge_node_id,
                learning_session.practice_assessment_id is None,
            )

    def _read_after_conflict(self, session_id: int, user_id: int, cause: IntegrityError) -> PracticeRead:
        with self.session.begin():
            learning_session = self._require_owned(session_id, user_id)
            task = self._practice_task(learning_session)
            assessment = self._practice_assessment(learning_session, user_id)
            if assessment is not None:
                return self._read(learning_session, assessment, task, reused=True)
        raise AdaptivePracticeError(
            "PRACTICE_STATE_CONFLICT",
            "Practice changed concurrently; retry the request.",
        ) from cause

    def _replay_answer(
        self,
        session_id: int,
        assessment_question_id: int,
        payload: PracticeAnswerCreate,
        cause: IntegrityError,
    ) -> PracticeRead:
        with self.session.begin():
            user_id = self._owner_id()
            learning_session = self._require_owned(session_id, user_id)
            task = self._practice_task(learning_session)
            assessment = self._practice_assessment(learning_session, user_id)
            if assessment is not None:
                question = next(
                    (item for item in assessment.questions if item.id == assessment_question_id),
                    None,
                )
                if question is not None and question.response is not None:
                    if question.response.answer_payload == payload.model_dump(mode="json"):
                        return self._read(learning_session, assessment, task, reused=True)
                    raise AdaptivePracticeError(
                        "PRACTICE_RESPONSE_LOCKED",
                        "A submitted practice answer cannot be changed.",
                    ) from cause
        raise AdaptivePracticeError(
            "PRACTICE_STATE_CONFLICT",
            "Practice changed concurrently; retry the request.",
        ) from cause

    def _practice_assessment(
        self,
        learning_session: LearningSession,
        user_id: int,
        *,
        for_update: bool = False,
    ) -> Assessment | None:
        if learning_session.practice_assessment_id is None:
            return None
        assessment = self.assessments.get_for_owner(
            learning_session.practice_assessment_id,
            user_id,
            load_history=True,
            for_update=for_update,
        )
        if (
            assessment is None
            or assessment.course_id != learning_session.course_id
            or assessment.assessment_type != AssessmentType.PRACTICE
        ):
            raise AdaptivePracticeError("PRACTICE_SCOPE_INVALID", "Practice state is outside this Session.")
        return assessment

    def _select_question(
        self,
        *,
        owner_id: int,
        course_id: int,
        node_id: int,
        desired: QuestionDifficulty,
        excluded: set[int],
    ):
        candidates = [
            item
            for item in self.questions.list_for_primary_node(course_id, node_id)
            if (
                item.validation_status == QuestionValidationStatus.VALIDATED
                or (
                    item.validation_status == QuestionValidationStatus.PENDING
                    and item.generation_metadata.get("practice_only") is True
                    and item.generation_metadata.get("validation") == "auto_checked"
                    and item.generation_metadata.get("auto_checked_content_version") == item.content_version
                    and item.source_refs
                )
            )
            and item.question_type in SUPPORTED_TYPES
            and item.id not in excluded
        ]
        seen_snapshots = list(
            self.session.scalars(
                select(AssessmentQuestion.question_snapshot)
                .join(Assessment, AssessmentQuestion.assessment_id == Assessment.id)
                .where(Assessment.owner_id == owner_id, Assessment.course_id == course_id)
            )
        )
        # A content revision is eligible only if its (ID, version) has not been
        # shown and its actual stem is different. A new ID alone is not enough.
        seen_versions = {
            (snapshot.get("source_question_id"), snapshot.get("source_question_version")) for snapshot in seen_snapshots
        }
        seen_stems = {normalize_question_stem(str(snapshot.get("stem", ""))) for snapshot in seen_snapshots}
        candidates = [
            item
            for item in candidates
            if (item.id, item.content_version) not in seen_versions
            and normalize_question_stem(item.stem)
            and normalize_question_stem(item.stem) not in seen_stems
        ]
        bucket = {difficulty: index for index, difficulty in enumerate(DIFFICULTY_FALLBACK[desired])}
        return min(candidates, key=lambda item: (bucket[item.difficulty], item.id), default=None)

    def _owner_id(self) -> int:
        owner = self.users.get_by_email(self.settings.legacy_bootstrap_user)
        if owner is None:
            raise AdaptivePracticeError("SESSION_NOT_FOUND", "Learning session not found.")
        return owner.id

    def _require_owned(self, session_id: int, user_id: int, *, for_update: bool = False) -> LearningSession:
        learning_session = self.sessions.get_owned(session_id=session_id, user_id=user_id, for_update=for_update)
        if learning_session is None:
            raise AdaptivePracticeError("SESSION_NOT_FOUND", "Learning session not found.")
        return learning_session

    def _require_practice_ready(self, learning_session: LearningSession) -> LearningSessionTaskState:
        if learning_session.status not in {LearningSessionStatus.CREATED, LearningSessionStatus.IN_PROGRESS}:
            raise AdaptivePracticeError("SESSION_NOT_WRITABLE", "This learning session is read-only.")
        if not learning_session.target_knowledge_node.is_active:
            raise AdaptivePracticeError("KNOWLEDGE_NODE_INACTIVE", "The learning target is no longer available.")
        task = self._practice_task(learning_session)
        if any(
            previous.status != LearningSessionTaskStatus.COMPLETED
            for previous in learning_session.tasks
            if previous.order_index < task.order_index
        ):
            raise AdaptivePracticeError("PRACTICE_NOT_READY", "Complete earlier learning phases first.")
        return task

    @staticmethod
    def _practice_task(learning_session: LearningSession) -> LearningSessionTaskState:
        task = next(
            (item for item in learning_session.tasks if item.phase == LearningSessionTaskPhase.ADAPTIVE_PRACTICE),
            None,
        )
        if task is None:
            raise AdaptivePracticeError("SESSION_TASK_NOT_FOUND", "Adaptive practice task not found.")
        return task

    @staticmethod
    def _start_task(learning_session: LearningSession, task: LearningSessionTaskState) -> None:
        now = datetime.now(timezone.utc)
        task.status = LearningSessionTaskStatus.IN_PROGRESS
        task.started_at = task.started_at or now
        if learning_session.status == LearningSessionStatus.CREATED:
            learning_session.status = LearningSessionStatus.IN_PROGRESS
            learning_session.started_at = learning_session.started_at or now

    @staticmethod
    def _set_progress(
        task: LearningSessionTaskState,
        difficulty: QuestionDifficulty,
        *,
        answered_count: int,
        bank_exhausted: bool,
    ) -> None:
        task.progress = {
            **task.progress,
            "answered_count": answered_count,
            "max_questions": _question_target(task),
            "current_difficulty": difficulty.value,
            "bank_exhausted": bank_exhausted,
        }

    @staticmethod
    def _complete_practice(
        assessment: Assessment, task: LearningSessionTaskState, *, mastered: bool = False, reason: str | None = None
    ) -> None:
        now = datetime.now(timezone.utc)
        assessment.status = AssessmentStatus.SUBMITTED
        assessment.submitted_at = assessment.submitted_at or now
        task.status = LearningSessionTaskStatus.COMPLETED
        task.completed_at = task.completed_at or now
        task.progress = {
            **task.progress,
            "completed": True,
            "completion_reason": reason or ("mastered" if mastered else "question_limit"),
        }

    @staticmethod
    def _read(
        learning_session: LearningSession,
        assessment: Assessment,
        task: LearningSessionTaskState,
        *,
        reused: bool = False,
    ) -> PracticeRead:
        try:
            pairs = _submitted_pairs(assessment)
            attempts = [_attempt_read(question, response) for question, response in pairs]
            current = _current_unanswered(assessment)
            completed = assessment.status == AssessmentStatus.SUBMITTED
            bank_empty = bool(task.progress.get("bank_exhausted")) and current is None
            correct = sum(item.is_correct for item in attempts)
            summary = None
            if completed:
                accuracy = (Decimal(correct) / Decimal(len(attempts))).quantize(Decimal("0.01"))
                summary = PracticeSummaryRead(
                    answered_count=len(attempts),
                    correct_count=correct,
                    accuracy=accuracy,
                )
            return PracticeRead(
                session_id=learning_session.id,
                knowledge_node_id=learning_session.target_knowledge_node_id,
                assessment_id=assessment.id,
                status="completed" if completed else "question_bank_empty" if bank_empty else "in_progress",
                current_difficulty=(
                    AssessmentQuestionSnapshotSchema.model_validate(current.question_snapshot).difficulty
                    if current is not None
                    else _stored_difficulty(task)
                ),
                current_question=_question_read(current) if current is not None else None,
                answered_count=len(attempts),
                max_questions=_question_target(task),
                attempts=attempts,
                summary=summary,
                completion_reason=task.progress.get("completion_reason") if completed else None,
                reused=reused,
            )
        except ValidationError as error:
            raise AdaptivePracticeError("QUESTION_SNAPSHOT_INVALID", "Stored practice question is invalid.") from error


def _initial_difficulty(mastery: KnowledgeNodeMasteryReadSchema | None) -> QuestionDifficulty:
    if mastery is None or mastery.calculation_state != KnowledgeStateAvailability.CALCULATED:
        return QuestionDifficulty.MEDIUM
    if mastery.confidence_level in {ConfidenceLevel.INSUFFICIENT, ConfidenceLevel.LOW}:
        return QuestionDifficulty.EASY
    if mastery.mastery_status in {MasteryStatus.NEEDS_ATTENTION, MasteryStatus.POSSIBLY_WEAK}:
        return QuestionDifficulty.EASY
    if mastery.mastery_status == MasteryStatus.GOOD_PERFORMANCE:
        return QuestionDifficulty.HARD
    return QuestionDifficulty.MEDIUM


def _question_target(task: LearningSessionTaskState) -> int:
    value = task.progress.get("max_questions")
    return (
        value if isinstance(value, int) and not isinstance(value, bool) and 2 <= value <= 5 else MAX_PRACTICE_QUESTIONS
    )


def _stored_difficulty(task: LearningSessionTaskState) -> QuestionDifficulty:
    raw = task.progress.get("current_difficulty", QuestionDifficulty.MEDIUM.value)
    try:
        return QuestionDifficulty(str(raw))
    except ValueError:
        return QuestionDifficulty.MEDIUM


def _submitted_pairs(assessment: Assessment) -> list[tuple[AssessmentQuestion, Response]]:
    return [
        (item, item.response)
        for item in sorted(assessment.questions, key=lambda row: (row.order_index, row.id or 0))
        if item.response is not None and item.response.submitted_at is not None
    ]


def _current_unanswered(assessment: Assessment) -> AssessmentQuestion | None:
    return next(
        (
            item
            for item in sorted(assessment.questions, key=lambda row: (row.order_index, row.id or 0))
            if item.response is None
        ),
        None,
    )


def _next_difficulty(attempts: list[tuple[AssessmentQuestion, Response]]) -> QuestionDifficulty:
    last_snapshot = AssessmentQuestionSnapshotSchema.model_validate(attempts[-1][0].question_snapshot)
    current_index = DIFFICULTY_ORDER.index(last_snapshot.difficulty)
    if len(attempts) >= 2 and all(response.is_correct is True for _, response in attempts[-2:]):
        return DIFFICULTY_ORDER[min(current_index + 1, len(DIFFICULTY_ORDER) - 1)]
    if len(attempts) >= 2 and all(response.is_correct is False for _, response in attempts[-2:]):
        return DIFFICULTY_ORDER[max(current_index - 1, 0)]
    return last_snapshot.difficulty


def _question_read(question: AssessmentQuestion) -> PracticeQuestionRead:
    snapshot = AssessmentQuestionSnapshotSchema.model_validate(question.question_snapshot)
    return PracticeQuestionRead(
        assessment_question_id=question.id,
        question_id=snapshot.source_question_id,
        question_number=question.order_index + 1,
        question_type=snapshot.question_type,
        stem=snapshot.stem,
        options=snapshot.options,
        difficulty=snapshot.difficulty,
        auto_checked=question.question_snapshot.get("auto_checked") is True,
    )


def _attempt_read(question: AssessmentQuestion, response: Response) -> PracticeAttemptRead:
    snapshot = AssessmentQuestionSnapshotSchema.model_validate(question.question_snapshot)
    return PracticeAttemptRead(
        attempt_id=response.id,
        assessment_question_id=question.id,
        question_id=snapshot.source_question_id,
        question_number=question.order_index + 1,
        question_type=snapshot.question_type,
        stem=snapshot.stem,
        options=snapshot.options,
        selected_options=list(response.answer_payload.get("selected_options", [])),
        correct_answer=snapshot.correct_answer,
        explanation=snapshot.explanation,
        difficulty=snapshot.difficulty,
        is_correct=response.is_correct is True,
        points_awarded=Decimal(response.points_awarded or 0),
        source_refs=snapshot.source_refs,
        submitted_at=response.submitted_at,
        auto_checked=question.question_snapshot.get("auto_checked") is True,
    )


def get_adaptive_practice_service(
    session: Session = Depends(get_db), settings: Settings = Depends(get_settings)
) -> AdaptivePracticeService:
    return AdaptivePracticeService(session, settings)


__all__ = [
    "AdaptivePracticeError",
    "AdaptivePracticeService",
    "MAX_PRACTICE_QUESTIONS",
    "get_adaptive_practice_service",
]
