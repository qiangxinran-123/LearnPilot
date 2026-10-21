from __future__ import annotations

import logging
from decimal import Decimal

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.settings import Settings, get_settings
from backend.app.db.models import Assessment, Course, User
from backend.app.db.session import get_db
from backend.app.models import AssessmentStatus
from backend.app.repositories import AssessmentRepository, ResponseRepository, UserRepository
from backend.app.schemas.assessment_scoring import AssessmentReadinessSchema
from backend.app.schemas.diagnostic import ObjectiveAnswerSchema
from backend.app.schemas.diagnostic_api import (
    DiagnosticAssessmentDetailSchema,
    DiagnosticAssessmentListSchema,
    DiagnosticAssessmentSummarySchema,
    DiagnosticCandidateQuestionSchema,
    DiagnosticResultSchema,
    SavedResponseSchema,
)
from backend.app.services.assessment_assembly_service import AssessmentAssemblyService
from backend.app.services.diagnostic_domain_service import DiagnosticDomainError, DiagnosticDomainService
from backend.app.services.diagnostic_evidence_ingestion import EvidenceIngestionError, EvidenceIngestionService
from backend.app.services.diagnostic_report_service import DiagnosticReportService

logger = logging.getLogger(__name__)


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
                    Assessment.status.in_([AssessmentStatus.READY, AssessmentStatus.IN_PROGRESS]),
                )
                .order_by(Assessment.id.desc())
            )
            existing_id = existing.id if existing is not None else None
        if existing_id is None:
            existing_id = (
                AssessmentAssemblyService(self.session).assemble_initial_diagnostic(owner_id, course_id).assessment.id
            )
        return self.get_assessment(existing_id)

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
                    .where(Assessment.owner_id == owner_id)
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
