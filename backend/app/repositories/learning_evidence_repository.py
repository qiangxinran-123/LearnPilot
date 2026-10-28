from __future__ import annotations

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from backend.app.db.models import Assessment, LearningEvidence, Response
from backend.app.models import AssessmentStatus, AssessmentType, EvidenceSourceType


class LearningEvidenceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, evidence: LearningEvidence) -> LearningEvidence:
        self.session.add(evidence)
        self.session.flush()
        return evidence

    def get_by_id(self, evidence_id: int) -> LearningEvidence | None:
        return self.session.get(LearningEvidence, evidence_id)

    def get_by_identity(
        self,
        *,
        source_type: EvidenceSourceType,
        source_question_snapshot_id: int,
        historical_knowledge_node_ref: int,
        evidence_schema_version: str,
    ) -> LearningEvidence | None:
        statement = select(LearningEvidence).where(
            LearningEvidence.source_type == source_type,
            LearningEvidence.source_question_snapshot_id == source_question_snapshot_id,
            LearningEvidence.historical_knowledge_node_ref == historical_knowledge_node_ref,
            LearningEvidence.evidence_schema_version == evidence_schema_version,
        )
        return self.session.scalar(statement)

    def list_by_source(self, source_type: EvidenceSourceType, source_assessment_id: int) -> list[LearningEvidence]:
        statement = (
            select(LearningEvidence)
            .where(
                LearningEvidence.source_type == source_type,
                LearningEvidence.source_assessment_id == source_assessment_id,
            )
            .order_by(LearningEvidence.id)
        )
        return list(self.session.scalars(statement))

    def list_by_course_and_user(self, course_id: int, user_id: int) -> list[LearningEvidence]:
        statement = (
            select(LearningEvidence)
            .where(LearningEvidence.course_id == course_id, LearningEvidence.user_id == user_id)
            .order_by(LearningEvidence.occurred_at, LearningEvidence.id)
        )
        return list(self.session.scalars(statement))

    def list_for_current_node(self, *, user_id: int, course_id: int, knowledge_node_id: int) -> list[LearningEvidence]:
        statement = (
            select(LearningEvidence)
            .where(
                LearningEvidence.user_id == user_id,
                LearningEvidence.course_id == course_id,
                LearningEvidence.current_knowledge_node_id == knowledge_node_id,
            )
            .order_by(
                LearningEvidence.source_assessment_id,
                LearningEvidence.source_question_snapshot_id,
                LearningEvidence.id,
            )
        )
        return list(self.session.scalars(statement))

    def list_submitted_for_current_nodes(
        self,
        *,
        user_id: int,
        course_id: int,
        knowledge_node_ids: list[int],
    ) -> list[LearningEvidence]:
        """Return only evidence whose immutable diagnostic source is safe to explain.

        This is deliberately a read-only authorization boundary for M5-D.  The
        joins prevent a malformed or manually inserted evidence row from exposing
        a draft response through an explanation endpoint.
        """
        if not knowledge_node_ids:
            return []
        statement = (
            select(LearningEvidence)
            .join(Assessment, Assessment.id == LearningEvidence.source_assessment_id)
            .join(Response, Response.id == LearningEvidence.source_response_id)
            .where(
                LearningEvidence.user_id == user_id,
                LearningEvidence.course_id == course_id,
                LearningEvidence.current_knowledge_node_id.in_(knowledge_node_ids),
                or_(
                    and_(
                        LearningEvidence.source_type == EvidenceSourceType.DIAGNOSTIC,
                        Assessment.assessment_type == AssessmentType.INITIAL_DIAGNOSTIC,
                    ),
                    and_(
                        LearningEvidence.source_type == EvidenceSourceType.PRACTICE,
                        Assessment.assessment_type == AssessmentType.PRACTICE,
                    ),
                ),
                Assessment.owner_id == user_id,
                Assessment.course_id == course_id,
                Assessment.status == AssessmentStatus.SUBMITTED,
                Response.assessment_id == LearningEvidence.source_assessment_id,
                Response.assessment_question_id == LearningEvidence.source_question_snapshot_id,
                Response.submitted_at.is_not(None),
                Response.points_awarded.is_not(None),
                Response.is_correct.is_not(None),
            )
            .order_by(
                LearningEvidence.current_knowledge_node_id,
                LearningEvidence.source_assessment_id,
                LearningEvidence.source_question_snapshot_id,
                LearningEvidence.id,
            )
        )
        return list(self.session.scalars(statement))
