from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.db.models import Assessment, AssessmentQuestion, Course, KnowledgeNode, Question
from backend.app.models import (
    AssessmentStatus,
    AssessmentType,
    KnowledgeImportance,
    KnowledgeRelationRole,
    QuestionDifficulty,
    QuestionType,
)
from backend.app.repositories import AssessmentRepository, QuestionRepository, ResponseRepository
from backend.app.schemas.assessment_scoring import (
    AssemblyMetadataSchema,
    AssessmentReadinessSchema,
    AssessmentScoreSummarySchema,
    CandidateAssessmentQuestionSchema,
    QuestionBankStatisticsSchema,
)
from backend.app.schemas.diagnostic import AssessmentQuestionSnapshotSchema
from backend.app.services.diagnostic_domain_service import DiagnosticDomainError, DiagnosticDomainService
from backend.app.services.diagnostic_question_quality import normalize_question_stem


class AssessmentAssemblyError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        statistics: QuestionBankStatisticsSchema | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.statistics = statistics
        super().__init__(message)


@dataclass(frozen=True)
class EligibleQuestion:
    question: Question
    primary_node: KnowledgeNode


@dataclass(frozen=True)
class AssembledAssessment:
    assessment: Assessment
    questions: tuple[AssessmentQuestion, ...]
    metadata: AssemblyMetadataSchema


class AssessmentAssemblyService:
    MIN_QUESTIONS = 8
    MAX_QUESTIONS = 20
    STRATEGY_VERSION = "knowledge_coverage_greedy_v1"
    _IMPORTANCE_RANK = {
        KnowledgeImportance.HIGH: 0,
        KnowledgeImportance.MEDIUM: 1,
        KnowledgeImportance.LOW: 2,
    }

    def __init__(self, session: Session) -> None:
        self.session = session
        self.questions = QuestionRepository(session)
        self.assessments = AssessmentRepository(session)
        self.responses = ResponseRepository(session)

    def assemble_initial_diagnostic(self, owner_id: int, course_id: int) -> AssembledAssessment:
        try:
            with self.session.begin():
                course = self.session.scalar(select(Course).where(Course.id == course_id, Course.owner_id == owner_id))
                if course is None:
                    raise AssessmentAssemblyError("COURSE_NOT_FOUND", "Course not found.")
                core_nodes = self._core_nodes(course_id)
                eligible = self._eligible_questions(course_id, {node.id for node in core_nodes})
                target = self._target_question_count(len(core_nodes), len(eligible))
                covered_ids = {item.primary_node.id for item in eligible}
                required_coverage_ids = {node.id for node in core_nodes[: min(len(core_nodes), target)]}
                statistics = QuestionBankStatisticsSchema(
                    available_questions=len(eligible),
                    eligible_knowledge_nodes=len(core_nodes),
                    covered_knowledge_nodes=len(covered_ids & {node.id for node in core_nodes}),
                    required_questions=max(self.MIN_QUESTIONS, target),
                )
                if target < self.MIN_QUESTIONS or not required_coverage_ids.issubset(covered_ids):
                    raise AssessmentAssemblyError(
                        "QUESTION_BANK_INSUFFICIENT",
                        "Validated question bank cannot meet the minimum count and core knowledge coverage.",
                        statistics=statistics,
                    )
                selected = self._select_questions(eligible, target)
                selected_node_ids = {item.primary_node.id for item in selected}
                if len(selected) != target or not required_coverage_ids.issubset(selected_node_ids):
                    raise AssessmentAssemblyError(
                        "QUESTION_BANK_INSUFFICIENT",
                        "Validated question bank cannot produce the required deterministic coverage.",
                        statistics=statistics,
                    )

                assessment = self.assessments.create(
                    Assessment(
                        course_id=course_id,
                        owner_id=owner_id,
                        assessment_type=AssessmentType.INITIAL_DIAGNOSTIC,
                        status=AssessmentStatus.DRAFT,
                    )
                )
                snapshots: list[AssessmentQuestion] = []
                for order_index, eligible_question in enumerate(selected):
                    snapshot = DiagnosticDomainService.build_question_snapshot(eligible_question.question)
                    snapshots.append(
                        self.assessments.add_question_snapshot(
                            AssessmentQuestion(
                                assessment_id=assessment.id,
                                question_id=eligible_question.question.id,
                                order_index=order_index,
                                question_snapshot=snapshot.model_dump(mode="json"),
                            )
                        )
                    )
                assessment.status = AssessmentStatus.READY
                metadata = self._metadata(selected, len(core_nodes))
                self.session.flush()
                return AssembledAssessment(assessment, tuple(snapshots), metadata)
        except IntegrityError as error:
            raise AssessmentAssemblyError(
                "ASSESSMENT_ASSEMBLY_FAILED", "Assessment could not be assembled atomically."
            ) from error

    def preview_readiness(self, owner_id: int, course_id: int) -> AssessmentReadinessSchema:
        """Return an assembly preview without creating or mutating an assessment."""
        with self.session.begin():
            course = self.session.scalar(select(Course).where(Course.id == course_id, Course.owner_id == owner_id))
            if course is None:
                raise AssessmentAssemblyError("COURSE_NOT_FOUND", "Course not found.")
            core_nodes = self._core_nodes(course_id)
            if not core_nodes:
                return AssessmentReadinessSchema(
                    course_id=course_id,
                    status="knowledge_not_ready",
                    can_start=False,
                    eligible_knowledge_nodes=0,
                    covered_knowledge_nodes=0,
                    available_questions=0,
                    message="No active course knowledge structure is available.",
                    reason_code="KNOWLEDGE_MODEL_NOT_READY",
                )
            eligible = self._eligible_questions(course_id, {node.id for node in core_nodes})
            target = self._target_question_count(len(core_nodes), len(eligible))
            covered_ids = {item.primary_node.id for item in eligible}
            required_ids = {node.id for node in core_nodes[: min(len(core_nodes), target)]}
            can_start = target >= self.MIN_QUESTIONS and required_ids.issubset(covered_ids)
            return AssessmentReadinessSchema(
                course_id=course_id,
                status="ready" if can_start else "question_bank_insufficient",
                can_start=can_start,
                estimated_question_count=target if can_start else None,
                estimated_minutes=max(5, round(target * 1.25)) if can_start else None,
                eligible_knowledge_nodes=len(core_nodes),
                covered_knowledge_nodes=len(covered_ids & {node.id for node in core_nodes}),
                available_questions=len(eligible),
                required_questions=max(self.MIN_QUESTIONS, target),
                message=(
                    "The course is ready for an initial diagnostic."
                    if can_start
                    else "The validated question bank cannot meet the minimum count and core coverage."
                ),
                reason_code=None if can_start else "QUESTION_BANK_INSUFFICIENT",
            )

    def candidate_questions(self, owner_id: int, assessment_id: int) -> list[CandidateAssessmentQuestionSchema]:
        with self.session.begin():
            assessment = self.assessments.get_for_owner(assessment_id, owner_id)
            if assessment is None:
                raise AssessmentAssemblyError("ASSESSMENT_NOT_FOUND", "Assessment not found.")
            return self.candidate_questions_from_loaded(assessment, self.assessments.list_questions(assessment.id))

    @staticmethod
    def candidate_questions_from_loaded(
        assessment: Assessment, questions: list[AssessmentQuestion]
    ) -> list[CandidateAssessmentQuestionSchema]:
        del assessment
        result: list[CandidateAssessmentQuestionSchema] = []
        for item in questions:
            try:
                snapshot = AssessmentQuestionSnapshotSchema.model_validate(item.question_snapshot)
            except ValidationError as error:
                raise AssessmentAssemblyError(
                    "QUESTION_SNAPSHOT_INVALID", "Stored question snapshot is invalid."
                ) from error
            result.append(
                CandidateAssessmentQuestionSchema(
                    assessment_question_id=item.id,
                    order_index=item.order_index,
                    question_type=snapshot.question_type,
                    stem=snapshot.stem,
                    options=snapshot.options,
                    difficulty=snapshot.difficulty,
                )
            )
        return result

    def score_summary(self, owner_id: int, assessment_id: int) -> AssessmentScoreSummarySchema:
        with self.session.begin():
            assessment = self.assessments.get_for_owner(assessment_id, owner_id)
            if assessment is None:
                raise AssessmentAssemblyError("ASSESSMENT_NOT_FOUND", "Assessment not found.")
            if assessment.status != AssessmentStatus.SUBMITTED:
                raise AssessmentAssemblyError("ASSESSMENT_NOT_SUBMITTED", "Assessment has not been submitted.")
            questions = self.assessments.list_questions(assessment.id)
            responses = self.responses.list_for_assessment(assessment.id)
            by_question = {response.assessment_question_id: response for response in responses}
            if set(by_question) != {question.id for question in questions} or any(
                response.is_correct is None or response.points_awarded is None for response in responses
            ):
                raise AssessmentAssemblyError(
                    "ASSESSMENT_SCORE_INCOMPLETE", "Persisted assessment scores are incomplete."
                )
            total_points = 0
            for question in questions:
                snapshot = AssessmentQuestionSnapshotSchema.model_validate(question.question_snapshot)
                total_points += snapshot.scoring_policy.max_points
            earned_points = sum((response.points_awarded for response in responses), start=0)
            answered = sum(bool(response.answer_payload.get("selected_options")) for response in responses)
            correct = sum(response.is_correct is True for response in responses)
            total = len(questions)
            return AssessmentScoreSummarySchema(
                assessment_id=assessment.id,
                total_questions=total,
                answered_questions=answered,
                correct_questions=correct,
                total_points=total_points,
                earned_points=earned_points,
                accuracy=(earned_points / total_points) if total_points else 0,
            )

    def _core_nodes(self, course_id: int) -> list[KnowledgeNode]:
        active_nodes = list(
            self.session.scalars(
                select(KnowledgeNode).where(
                    KnowledgeNode.course_id == course_id,
                    KnowledgeNode.is_active.is_(True),
                )
            )
        )
        core = [node for node in active_nodes if node.importance != KnowledgeImportance.LOW] or active_nodes
        return sorted(core, key=lambda node: (self._IMPORTANCE_RANK[node.importance], node.id))

    def _eligible_questions(self, course_id: int, core_node_ids: set[int]) -> list[EligibleQuestion]:
        result: list[EligibleQuestion] = []
        seen_stems: set[str] = set()
        for question in self.questions.list_validated_for_course(course_id):
            try:
                content = DiagnosticDomainService.build_question_snapshot(question)
            except DiagnosticDomainError:
                continue
            if not content.source_refs:
                continue
            primary_links = [
                link
                for link in question.knowledge_links
                if link.relation_role == KnowledgeRelationRole.PRIMARY
                and link.knowledge_node is not None
                and link.knowledge_node.is_active
                and link.knowledge_node.id in core_node_ids
            ]
            if len(primary_links) != 1:
                continue
            normalized_stem = normalize_question_stem(question.stem)
            if not normalized_stem or normalized_stem in seen_stems:
                continue
            seen_stems.add(normalized_stem)
            result.append(EligibleQuestion(question, primary_links[0].knowledge_node))
        return result

    def _target_question_count(self, core_node_count: int, available_count: int) -> int:
        if core_node_count <= 4:
            recommended = 8
        elif core_node_count <= 10:
            recommended = max(10, min(15, (core_node_count * 5 + 3) // 4))
        else:
            recommended = max(15, min(self.MAX_QUESTIONS, (core_node_count * 5 + 3) // 4))
        return min(recommended, available_count, self.MAX_QUESTIONS)

    def _select_questions(self, eligible: list[EligibleQuestion], target: int) -> list[EligibleQuestion]:
        desired_types = self._type_targets(target)
        desired_difficulties = self._difficulty_targets(target)
        selected: list[EligibleQuestion] = []
        selected_ids: set[int] = set()
        covered_nodes: set[int] = set()
        node_counts: Counter[int] = Counter()
        type_counts: Counter[QuestionType] = Counter()
        difficulty_counts: Counter[QuestionDifficulty] = Counter()

        while len(selected) < target:
            candidates = [item for item in eligible if item.question.id not in selected_ids]
            if not candidates:
                break

            def rank(item: EligibleQuestion) -> tuple[int, int, int, int, int, int]:
                node_id = item.primary_node.id
                uncovered_rank = 0 if node_id not in covered_nodes else 1
                coverage_rank = (
                    self._IMPORTANCE_RANK[item.primary_node.importance] if uncovered_rank == 0 else node_counts[node_id]
                )
                type_need = desired_types[item.question.question_type] - type_counts[item.question.question_type]
                difficulty_need = (
                    desired_difficulties[item.question.difficulty] - difficulty_counts[item.question.difficulty]
                )
                return (
                    uncovered_rank,
                    coverage_rank,
                    -max(type_need, 0),
                    -max(difficulty_need, 0),
                    self._IMPORTANCE_RANK[item.primary_node.importance],
                    item.question.id,
                )

            chosen = min(candidates, key=rank)
            selected.append(chosen)
            selected_ids.add(chosen.question.id)
            covered_nodes.add(chosen.primary_node.id)
            node_counts[chosen.primary_node.id] += 1
            type_counts[chosen.question.question_type] += 1
            difficulty_counts[chosen.question.difficulty] += 1
        return selected

    def _metadata(self, selected: list[EligibleQuestion], eligible_node_count: int) -> AssemblyMetadataSchema:
        return AssemblyMetadataSchema(
            strategy_version=self.STRATEGY_VERSION,
            question_count=len(selected),
            eligible_knowledge_nodes=eligible_node_count,
            covered_knowledge_nodes=len({item.primary_node.id for item in selected}),
            question_type_distribution=dict(Counter(item.question.question_type for item in selected)),
            difficulty_distribution=dict(Counter(item.question.difficulty for item in selected)),
        )

    @staticmethod
    def _type_targets(count: int) -> dict[QuestionType, int]:
        single = round(count * 0.7)
        true_false = round(count * 0.2)
        return {
            QuestionType.SINGLE_CHOICE: single,
            QuestionType.TRUE_FALSE: true_false,
            QuestionType.MULTIPLE_CHOICE: count - single - true_false,
        }

    @staticmethod
    def _difficulty_targets(count: int) -> dict[QuestionDifficulty, int]:
        easy = round(count * 0.3)
        medium = round(count * 0.5)
        return {
            QuestionDifficulty.EASY: easy,
            QuestionDifficulty.MEDIUM: medium,
            QuestionDifficulty.HARD: count - easy - medium,
        }


__all__ = ["AssembledAssessment", "AssessmentAssemblyError", "AssessmentAssemblyService"]
