from __future__ import annotations

import logging
from decimal import Decimal
from threading import Lock

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.settings import Settings, get_settings
from backend.app.db.models import Assessment, Course, LearningEvidence, User
from backend.app.db.session import get_db
from backend.app.models import (
    AssessmentStatus,
    AssessmentType,
    QuestionDifficulty,
    QuestionType,
    QuestionValidationStatus,
)
from backend.app.repositories import AssessmentRepository, ResponseRepository, UserRepository
from backend.app.schemas.assessment_scoring import AssessmentReadinessSchema
from backend.app.schemas.diagnostic import ObjectiveAnswerSchema
from backend.app.schemas.diagnostic_api import (
    DiagnosticAssessmentDetailSchema,
    DiagnosticAssessmentDiscardSchema,
    DiagnosticAssessmentListSchema,
    DiagnosticAssessmentSummarySchema,
    DiagnosticCandidateQuestionSchema,
    DiagnosticResultSchema,
    SavedResponseSchema,
)
from backend.app.services.assessment_assembly_service import AssessmentAssemblyService
from backend.app.services.diagnostic_domain_service import DiagnosticDomainError, DiagnosticDomainService
from backend.app.services.diagnostic_evidence_ingestion import EvidenceIngestionError, EvidenceIngestionService
from backend.app.services.diagnostic_question_generation import DiagnosticQuestionGenerationService
from backend.app.services.diagnostic_report_service import DiagnosticReportService
from backend.app.services.mastery_service import MasteryService, MasteryServiceError

logger = logging.getLogger(__name__)
_diagnostic_generation_locks_guard = Lock()
_diagnostic_generation_locks: dict[tuple[int, int], Lock] = {}


def _generation_lock(owner_id: int, course_id: int) -> Lock:
    with _diagnostic_generation_locks_guard:
        return _diagnostic_generation_locks.setdefault((owner_id, course_id), Lock())


class DiagnosticExperienceService:
    """M4-D application boundary around M4-A/C domain services."""

    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.assessments = AssessmentRepository(session)
        self.responses = ResponseRepository(session)

    def readiness(self, course_id: int) -> AssessmentReadinessSchema:
        return AssessmentAssemblyService(self.session).preview_readiness(self._owner_id(), course_id)

    def create_or_resume(self, course_id: int) -> DiagnosticAssessmentDetailSchema:
        owner_id = self._owner_id()
        with self.session.begin():
            course = self.session.scalar(select(Course).where(Course.id == course_id, Course.owner_id == owner_id))
            if course is None:
                raise DiagnosticDomainError("COURSE_NOT_FOUND", "Course not found.")
            existing = self.session.scalar(
                select(Assessment)
                .where(
                    Assessment.course_id == course_id,
                    Assessment.owner_id == owner_id,
                    Assessment.assessment_type == AssessmentType.INITIAL_DIAGNOSTIC,
                    Assessment.status.in_([AssessmentStatus.READY, AssessmentStatus.IN_PROGRESS]),
                )
                .order_by(Assessment.id.desc())
            )
            existing_id = existing.id if existing is not None else None
        if existing_id is None:
            lock = _generation_lock(owner_id, course_id)
            if not lock.acquire(blocking=False):
                raise DiagnosticDomainError("DIAGNOSTIC_GENERATION_BUSY", "正在生成诊断题，请稍后重试。")
            try:
                existing_id = self._create_with_fresh_questions(owner_id, course_id)
            finally:
                lock.release()
        return self.get_assessment(existing_id)

    def _create_with_fresh_questions(self, owner_id: int, course_id: int) -> int:
        assembler = AssessmentAssemblyService(self.session)
        generator = DiagnosticQuestionGenerationService(
            self.session, self.settings.model_copy(update={"llm_max_attempts": 1})
        )
        for attempt in range(self.settings.diagnostic_replenish_max_calls + 1):
            with self.session.begin():
                current = self.session.scalar(
                    select(Assessment.id)
                    .where(
                        Assessment.owner_id == owner_id,
                        Assessment.course_id == course_id,
                        Assessment.assessment_type == AssessmentType.INITIAL_DIAGNOSTIC,
                        Assessment.status.in_([AssessmentStatus.READY, AssessmentStatus.IN_PROGRESS]),
                    )
                    .order_by(Assessment.id.desc())
                )
                if current is not None:
                    return current
                nodes = assembler._core_nodes(course_id)
                eligible = assembler._eligible_questions(course_id, {node.id for node in nodes})
                unseen = assembler._unseen_questions(owner_id, course_id, eligible)
                required = nodes[: assembler.MIN_QUESTIONS]
                covered = {item.primary_node.id for item in unseen}
                missing = [node.id for node in required if node.id not in covered]
                ready = len(unseen) >= assembler.MIN_QUESTIONS and not missing
                node_ids = [node.id for node in required]
            if ready:
                return assembler.assemble_initial_diagnostic(owner_id, course_id, unseen_only=True).assessment.id
            if not node_ids:
                raise DiagnosticDomainError("KNOWLEDGE_MODEL_NOT_READY", "课程知识结构尚未准备好。")
            if attempt == self.settings.diagnostic_replenish_max_calls:
                raise DiagnosticDomainError("DIAGNOSTIC_GENERATION_LIMIT", "本次补题数量达到上限，请重试继续。")
            generator.generate_questions_for_node(
                owner_id=owner_id,
                course_id=course_id,
                knowledge_node_id=missing[0] if missing else node_ids[attempt % len(node_ids)],
                question_type=QuestionType.SINGLE_CHOICE,
                difficulty=QuestionDifficulty.MEDIUM,
                count=1,
                initial_status=QuestionValidationStatus.PENDING,
                diagnostic_auto_checked=True,
            )
        raise AssertionError("unreachable")

    def start(self, assessment_id: int) -> DiagnosticAssessmentDetailSchema:
        owner_id = self._owner_id()
        with self.session.begin():
            assessment = self.assessments.get_for_owner(assessment_id, owner_id)
            if assessment is None:
                raise DiagnosticDomainError("ASSESSMENT_NOT_FOUND", "Assessment not found.")
            status = assessment.status
        if status == AssessmentStatus.READY:
            DiagnosticDomainService(self.session).start_assessment(owner_id, assessment_id)
        elif status not in {AssessmentStatus.IN_PROGRESS, AssessmentStatus.SUBMITTED}:
            raise DiagnosticDomainError("ASSESSMENT_INVALID_TRANSITION", "Assessment cannot be started.")
        return self.get_assessment(assessment_id)

    def save_response(
        self, assessment_id: int, assessment_question_id: int, answer: ObjectiveAnswerSchema
    ) -> SavedResponseSchema:
        response = DiagnosticDomainService(self.session).save_draft_response(
            self._owner_id(), assessment_id, assessment_question_id, answer
        )
        return SavedResponseSchema(
            assessment_question_id=response.assessment_question_id,
            selected_options=list(response.answer_payload.get("selected_options", [])),
            answered_at=response.answered_at,
        )

    def discard(self, assessment_id: int) -> DiagnosticAssessmentDiscardSchema:
        DiagnosticDomainService(self.session).discard_assessment(self._owner_id(), assessment_id)
        return DiagnosticAssessmentDiscardSchema(assessment_id=assessment_id)

    def submit(self, assessment_id: int) -> DiagnosticResultSchema:
        owner_id = self._owner_id()
        assessment = DiagnosticDomainService(self.session).submit_assessment(owner_id, assessment_id)
        submitted_assessment_id = assessment.id
        submitted_course_id = assessment.course_id
        try:
            result = EvidenceIngestionService(self.session).ingest_assessment(
                submitted_assessment_id,
                expected_user_id=owner_id,
                expected_course_id=submitted_course_id,
            )
            with self.session.begin():
                node_ids = list(
                    self.session.scalars(
                        select(LearningEvidence.current_knowledge_node_id)
                        .where(
                            LearningEvidence.source_assessment_id == submitted_assessment_id,
                            LearningEvidence.user_id == owner_id,
                            LearningEvidence.course_id == submitted_course_id,
                            LearningEvidence.current_knowledge_node_id.is_not(None),
                        )
                        .distinct()
                    )
                )
            try:
                for node_id in node_ids:
                    MasteryService(self.session).refresh_state(
                        user_id=owner_id, course_id=submitted_course_id, knowledge_node_id=node_id
                    )
            except MasteryServiceError as error:
                logger.exception(
                    "Diagnostic mastery refresh failed after evidence sync",
                    extra={"assessment_id": submitted_assessment_id, "error_code": error.code},
                )
                raise DiagnosticDomainError(
                    "MASTERY_REFRESH_FAILED", "Diagnostic was saved but mastery could not be refreshed; retry."
                ) from error
            if result.issues:
                logger.warning(
                    "Diagnostic evidence sync completed with skipped invalid sources",
                    extra={
                        "assessment_id": submitted_assessment_id,
                        "issue_codes": [issue.code for issue in result.issues],
                    },
                )
        except EvidenceIngestionError as error:
            logger.exception(
                "Diagnostic evidence sync failed after assessment commit",
                extra={"assessment_id": submitted_assessment_id, "error_code": error.code},
            )
        return self.result(assessment_id)

    def get_assessment(self, assessment_id: int) -> DiagnosticAssessmentDetailSchema:
        owner_id = self._owner_id()
        with self.session.begin():
            assessment = self.assessments.get_for_owner(assessment_id, owner_id)
            if assessment is None:
                raise DiagnosticDomainError("ASSESSMENT_NOT_FOUND", "Assessment not found.")
            questions = AssessmentAssemblyService(self.session).candidate_questions_from_loaded(
                assessment, self.assessments.list_questions(assessment.id)
            )
            responses = {
                item.assessment_question_id: item for item in self.responses.list_for_assessment(assessment.id)
            }
            candidate_rows = [
                DiagnosticCandidateQuestionSchema(
                    **item.model_dump(mode="python"),
                    saved_answer=(
                        list(responses[item.assessment_question_id].answer_payload.get("selected_options", []))
                        if item.assessment_question_id in responses
                        else None
                    ),
                )
                for item in questions
            ]
            return DiagnosticAssessmentDetailSchema(
                id=assessment.id,
                course_id=assessment.course_id,
                course_name=assessment.course.name,
                status=assessment.status,
                questions=candidate_rows,
                question_count=len(candidate_rows),
                answered_count=sum(bool(item.saved_answer) for item in candidate_rows),
                created_at=assessment.created_at,
                started_at=assessment.started_at,
                submitted_at=assessment.submitted_at,
            )

    def list_assessments(self) -> DiagnosticAssessmentListSchema:
        owner_id = self._owner_id()
        with self.session.begin():
            assessments = list(
                self.session.scalars(
                    select(Assessment)
                    .where(
                        Assessment.owner_id == owner_id, Assessment.assessment_type == AssessmentType.INITIAL_DIAGNOSTIC
                    )
                    .order_by(Assessment.created_at.desc(), Assessment.id.desc())
                )
            )
            summaries: list[DiagnosticAssessmentSummarySchema] = []
            for assessment in assessments:
                questions = self.assessments.list_questions(assessment.id)
                responses = self.responses.list_for_assessment(assessment.id)
                correct: int | None = None
                accuracy: Decimal | None = None
                if assessment.status == AssessmentStatus.SUBMITTED and questions:
                    correct = sum(item.is_correct is True for item in responses)
                    accuracy = Decimal(correct) / Decimal(len(questions))
                summaries.append(
                    DiagnosticAssessmentSummarySchema(
                        id=assessment.id,
                        course_id=assessment.course_id,
                        course_name=assessment.course.name,
                        status=assessment.status,
                        question_count=len(questions),
                        answered_count=sum(bool(item.answer_payload.get("selected_options")) for item in responses),
                        correct_questions=correct,
                        accuracy=accuracy,
                        created_at=assessment.created_at,
                        submitted_at=assessment.submitted_at,
                    )
                )
            return DiagnosticAssessmentListSchema(count=len(summaries), assessments=summaries)

    def result(self, assessment_id: int) -> DiagnosticResultSchema:
        return DiagnosticReportService(self.session).build_report(self._owner_id(), assessment_id)

    def _owner_id(self) -> int:
        with self.session.begin():
            users = UserRepository(self.session)
            owner = users.get_by_email(self.settings.legacy_bootstrap_user)
            if owner is None:
                owner = users.add(
                    User(
                        email=self.settings.legacy_bootstrap_user,
                        display_name=self.settings.legacy_bootstrap_user_display_name,
                        is_active=True,
                    )
                )
            return owner.id


def get_diagnostic_experience_service(
    session: Session = Depends(get_db), settings: Settings = Depends(get_settings)
) -> DiagnosticExperienceService:
    return DiagnosticExperienceService(session, settings)


__all__ = ["DiagnosticExperienceService", "get_diagnostic_experience_service"]
