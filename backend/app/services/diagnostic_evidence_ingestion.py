from __future__ import annotations

from contextlib import nullcontext
from datetime import timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.db.models import Assessment, AssessmentQuestion, KnowledgeNode, Response
from backend.app.models import AssessmentStatus, AssessmentType, EvidenceSourceType
from backend.app.repositories import LearningEvidenceRepository
from backend.app.schemas.diagnostic import AssessmentQuestionSnapshotSchema
from backend.app.schemas.evidence_ingestion import (
    EvidenceExtractionIssueSchema,
    EvidenceExtractionPlanSchema,
    EvidenceIngestionResultSchema,
)
from backend.app.schemas.learning_evidence import LearningEvidenceCreateSchema
from backend.app.services.learning_evidence_service import LearningEvidenceError, LearningEvidenceService

EVIDENCE_SCHEMA_VERSION = "learning_evidence_v1"
_DECIMAL_QUANTUM = Decimal("0.00001")


class EvidenceIngestionError(ValueError):
    def __init__(self, code: str, message: str, *, assessment_id: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.assessment_id = assessment_id


class DiagnosticEvidenceExtractor:
    """Pure M4-fact reader: it normalizes persisted scores without rescoring answers."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def extract_assessment(
        self,
        assessment_id: int,
        *,
        expected_user_id: int | None = None,
        expected_course_id: int | None = None,
        in_transaction: bool = False,
    ) -> EvidenceExtractionPlanSchema:
        with nullcontext() if in_transaction else self.session.begin():
            assessment = self.session.get(Assessment, assessment_id)
            if assessment is None:
                raise EvidenceIngestionError(
                    "ASSESSMENT_NOT_FOUND",
                    "Assessment was not found.",
                    assessment_id=assessment_id,
                )
            if expected_user_id is not None and assessment.owner_id != expected_user_id:
                raise EvidenceIngestionError(
                    "SOURCE_OWNERSHIP_MISMATCH",
                    "Assessment does not belong to the expected user.",
                    assessment_id=assessment_id,
                )
            if expected_course_id is not None and assessment.course_id != expected_course_id:
                raise EvidenceIngestionError(
                    "SOURCE_OWNERSHIP_MISMATCH",
                    "Assessment does not belong to the expected course.",
                    assessment_id=assessment_id,
                )
            if assessment.status != AssessmentStatus.SUBMITTED:
                raise EvidenceIngestionError(
                    "ASSESSMENT_NOT_SUBMITTED",
                    "Only submitted assessments can produce learning evidence.",
                    assessment_id=assessment_id,
                )
            if assessment.assessment_type == AssessmentType.PRACTICE and not in_transaction:
                raise EvidenceIngestionError(
                    "SOURCE_TYPE_UNSUPPORTED",
                    "Practice evidence is created by session settlement.",
                    assessment_id=assessment_id,
                )

            questions = list(
                self.session.scalars(
                    select(AssessmentQuestion)
                    .where(AssessmentQuestion.assessment_id == assessment.id)
                    .order_by(AssessmentQuestion.order_index)
                )
            )
            responses = {
                response.assessment_question_id: response
                for response in self.session.scalars(select(Response).where(Response.assessment_id == assessment.id))
            }
            candidates: list[LearningEvidenceCreateSchema] = []
            issues: list[EvidenceExtractionIssueSchema] = []
            for question in questions:
                response = responses.get(question.id)
                if (
                    response is None
                    or response.submitted_at is None
                    or response.points_awarded is None
                    or response.is_correct is None
                ):
                    issues.append(
                        self._issue(
                            "SCORING_INCOMPLETE",
                            assessment.id,
                            question.id,
                            "Question has no submitted, persisted deterministic score.",
                        )
                    )
                    continue
                try:
                    snapshot = AssessmentQuestionSnapshotSchema.model_validate(question.question_snapshot)
                except ValidationError:
                    issues.append(
                        self._issue(
                            "INVALID_QUESTION_SNAPSHOT",
                            assessment.id,
                            question.id,
                            "Stored question snapshot is invalid.",
                        )
                    )
                    continue

                try:
                    points = Decimal(response.points_awarded)
                    maximum = Decimal(snapshot.scoring_policy.max_points)
                    if maximum <= 0 or points < 0 or points > maximum:
                        raise InvalidOperation
                    normalized_score = (points / maximum).quantize(_DECIMAL_QUANTUM, rounding=ROUND_HALF_UP)
                except InvalidOperation, ValueError:
                    issues.append(
                        self._issue(
                            "INVALID_NORMALIZED_SCORE",
                            assessment.id,
                            question.id,
                            "Persisted points and snapshot maximum cannot form a score in [0, 1].",
                        )
                    )
                    continue

                node_ids = [node.id for node in snapshot.knowledge_nodes]
                current_nodes = {
                    node.id
                    for node in self.session.scalars(
                        select(KnowledgeNode).where(
                            KnowledgeNode.course_id == assessment.course_id,
                            KnowledgeNode.id.in_(node_ids),
                            KnowledgeNode.is_active.is_(True),
                        )
                    )
                }
                weight = (Decimal(1) / Decimal(len(node_ids))).quantize(_DECIMAL_QUANTUM, rounding=ROUND_HALF_UP)
                occurred_at = response.submitted_at
                if occurred_at.tzinfo is None:
                    occurred_at = occurred_at.replace(tzinfo=timezone.utc)
                for historical_node_id in node_ids:
                    candidates.append(
                        LearningEvidenceCreateSchema(
                            user_id=assessment.owner_id,
                            course_id=assessment.course_id,
                            source_type=(
                                EvidenceSourceType.PRACTICE
                                if assessment.assessment_type == AssessmentType.PRACTICE
                                else EvidenceSourceType.DIAGNOSTIC
                            ),
                            source_assessment_id=assessment.id,
                            source_question_snapshot_id=question.id,
                            source_response_id=response.id,
                            historical_knowledge_node_ref=historical_node_id,
                            current_knowledge_node_id=(
                                historical_node_id if historical_node_id in current_nodes else None
                            ),
                            knowledge_model_version=snapshot.knowledge_model_version,
                            normalized_score=normalized_score,
                            difficulty=snapshot.difficulty,
                            attribution_weight=weight,
                            source_scoring_version=snapshot.scoring_policy.version,
                            evidence_schema_version=EVIDENCE_SCHEMA_VERSION,
                            occurred_at=occurred_at,
                        )
                    )

            return EvidenceExtractionPlanSchema(
                assessment_id=assessment.id,
                user_id=assessment.owner_id,
                course_id=assessment.course_id,
                candidates=candidates,
                issues=issues,
            )

    @staticmethod
    def _issue(
        code: str,
        assessment_id: int,
        source_question_snapshot_id: int,
        message: str,
    ) -> EvidenceExtractionIssueSchema:
        return EvidenceExtractionIssueSchema(
            code=code,
            assessment_id=assessment_id,
            source_question_snapshot_id=source_question_snapshot_id,
            message=message,
        )


class EvidenceIngestionService:
    """Idempotent persistence boundary shared by submit synchronization and backfill."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = LearningEvidenceRepository(session)
        self.extractor = DiagnosticEvidenceExtractor(session)

    def ingest_assessment(
        self,
        assessment_id: int,
        *,
        expected_user_id: int | None = None,
        expected_course_id: int | None = None,
        dry_run: bool = False,
    ) -> EvidenceIngestionResultSchema:
        plan = self.extractor.extract_assessment(
            assessment_id,
            expected_user_id=expected_user_id,
            expected_course_id=expected_course_id,
        )
        created = 0
        skipped = 0
        for candidate in plan.candidates:
            if self._already_exists(candidate):
                skipped += 1
                continue
            if dry_run:
                continue
            try:
                LearningEvidenceService(self.session).create(candidate)
                created += 1
            except IntegrityError as error:
                if self._already_exists(candidate):
                    skipped += 1
                    continue
                raise EvidenceIngestionError(
                    "EVIDENCE_PERSISTENCE_FAILED",
                    "Evidence insert violated a non-idempotency database constraint.",
                    assessment_id=assessment_id,
                ) from error
            except LearningEvidenceError as error:
                raise EvidenceIngestionError(
                    error.code,
                    str(error),
                    assessment_id=assessment_id,
                ) from error
            except (SQLAlchemyError, RuntimeError) as error:
                raise EvidenceIngestionError(
                    "EVIDENCE_PERSISTENCE_FAILED",
                    "Evidence persistence failed after the diagnostic had been committed.",
                    assessment_id=assessment_id,
                ) from error

        return EvidenceIngestionResultSchema(
            assessment_id=assessment_id,
            candidates=len(plan.candidates),
            created=created,
            skipped=skipped,
            unavailable_historical_nodes=sum(
                candidate.current_knowledge_node_id is None for candidate in plan.candidates
            ),
            dry_run=dry_run,
            skip_reasons={"SKIPPED_ALREADY_EXISTS": skipped} if skipped else {},
            issues=plan.issues,
        )

    def _already_exists(self, candidate: LearningEvidenceCreateSchema) -> bool:
        with self.session.begin():
            return (
                self.repository.get_by_identity(
                    source_type=candidate.source_type,
                    source_question_snapshot_id=candidate.source_question_snapshot_id,
                    historical_knowledge_node_ref=candidate.historical_knowledge_node_ref,
                    evidence_schema_version=candidate.evidence_schema_version,
                )
                is not None
            )


__all__ = [
    "DiagnosticEvidenceExtractor",
    "EVIDENCE_SCHEMA_VERSION",
    "EvidenceIngestionError",
    "EvidenceIngestionService",
]
