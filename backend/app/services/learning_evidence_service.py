from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.app.db.models import Assessment, AssessmentQuestion, KnowledgeNode, LearningEvidence, Response
from backend.app.models import AssessmentStatus, EvidenceSourceType
from backend.app.repositories import LearningEvidenceRepository
from backend.app.schemas.diagnostic import AssessmentQuestionSnapshotSchema
from backend.app.schemas.learning_evidence import LearningEvidenceCreateSchema


class LearningEvidenceError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class LearningEvidenceService:
    """Validates source identity and ownership; it never derives or recalculates scores."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = LearningEvidenceRepository(session)

    @staticmethod
    def _utc_naive(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def create(self, payload: LearningEvidenceCreateSchema) -> LearningEvidence:
        with self.session.begin():
            assessment = self.session.get(Assessment, payload.source_assessment_id)
            if assessment is None:
                raise LearningEvidenceError("SOURCE_ASSESSMENT_NOT_FOUND", "Source assessment was not found.")
            if assessment.owner_id != payload.user_id or assessment.course_id != payload.course_id:
                raise LearningEvidenceError(
                    "SOURCE_OWNERSHIP_MISMATCH",
                    "Evidence owner and course must match the source assessment.",
                )
            if assessment.status != AssessmentStatus.SUBMITTED:
                raise LearningEvidenceError(
                    "SOURCE_ASSESSMENT_NOT_SUBMITTED",
                    "Diagnostic evidence requires a submitted assessment.",
                )
            if payload.source_type != EvidenceSourceType.DIAGNOSTIC:
                raise LearningEvidenceError("SOURCE_TYPE_UNSUPPORTED", "Only diagnostic evidence is writable in M5-A.")

            snapshot_row = self.session.get(AssessmentQuestion, payload.source_question_snapshot_id)
            if snapshot_row is None or snapshot_row.assessment_id != assessment.id:
                raise LearningEvidenceError(
                    "SOURCE_SNAPSHOT_MISMATCH",
                    "Source question snapshot does not belong to the assessment.",
                )
            response = self.session.get(Response, payload.source_response_id)
            if (
                response is None
                or response.assessment_id != assessment.id
                or response.assessment_question_id != snapshot_row.id
            ):
                raise LearningEvidenceError(
                    "SOURCE_RESPONSE_MISMATCH",
                    "Source response does not belong to the assessment question snapshot.",
                )
            if response.submitted_at is None or response.points_awarded is None or response.is_correct is None:
                raise LearningEvidenceError(
                    "SOURCE_RESPONSE_NOT_SCORED",
                    "Diagnostic evidence requires a submitted, deterministically scored response.",
                )

            snapshot = AssessmentQuestionSnapshotSchema.model_validate(snapshot_row.question_snapshot)
            node_ids = {node.id for node in snapshot.knowledge_nodes}
            if payload.historical_knowledge_node_ref not in node_ids:
                raise LearningEvidenceError(
                    "HISTORICAL_NODE_NOT_IN_SNAPSHOT",
                    "Historical knowledge node must be present in the immutable snapshot.",
                )
            if payload.current_knowledge_node_id is not None:
                current_node = self.session.get(KnowledgeNode, payload.current_knowledge_node_id)
                if (
                    current_node is None
                    or current_node.id != payload.historical_knowledge_node_ref
                    or current_node.course_id != assessment.course_id
                    or not current_node.is_active
                ):
                    raise LearningEvidenceError(
                        "INVALID_KNOWLEDGE_REFERENCE",
                        "Current knowledge node must be the same active node in the assessment course.",
                    )
            if payload.difficulty != snapshot.difficulty:
                raise LearningEvidenceError(
                    "SOURCE_DIFFICULTY_MISMATCH",
                    "Difficulty must match the immutable snapshot.",
                )
            if payload.knowledge_model_version != snapshot.knowledge_model_version:
                raise LearningEvidenceError(
                    "SOURCE_KNOWLEDGE_VERSION_MISMATCH",
                    "Knowledge model version must match the immutable snapshot.",
                )
            if payload.source_scoring_version != snapshot.scoring_policy.version:
                raise LearningEvidenceError(
                    "SOURCE_SCORING_VERSION_MISMATCH",
                    "Scoring version must match the immutable snapshot.",
                )
            if self._utc_naive(payload.occurred_at) != self._utc_naive(response.submitted_at):
                raise LearningEvidenceError(
                    "SOURCE_OCCURRED_AT_MISMATCH",
                    "occurred_at must equal the original response submission time.",
                )

            return self.repository.create(LearningEvidence(**payload.model_dump()))
