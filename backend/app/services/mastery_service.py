from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.db.models import Course, KnowledgeNode, StudentKnowledgeState
from backend.app.repositories import LearningEvidenceRepository, StudentKnowledgeStateRepository
from backend.app.schemas.mastery import (
    KnowledgeStateRefreshResultSchema,
    MasteryEvidenceSchema,
    StudentKnowledgeStateSchema,
)
from backend.app.services.confidence_estimator import ConfidenceEstimator
from backend.app.services.evidence_fingerprint import calculate_evidence_fingerprint
from backend.app.services.mastery_calculator import MasteryCalculationError, MasteryCalculator
from backend.app.services.mastery_config import MASTERY_V1_CONFIG, MasteryAlgorithmConfig


class MasteryServiceError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class MasteryService:
    def __init__(
        self,
        session: Session,
        *,
        config: MasteryAlgorithmConfig = MASTERY_V1_CONFIG,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.session = session
        self.config = config
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.evidence_repository = LearningEvidenceRepository(session)
        self.state_repository = StudentKnowledgeStateRepository(session)
        self.calculator = MasteryCalculator(config)
        self.confidence_estimator = ConfidenceEstimator(config)

    def refresh_state(
        self,
        *,
        user_id: int,
        course_id: int,
        knowledge_node_id: int,
    ) -> KnowledgeStateRefreshResultSchema:
        try:
            with self.session.begin():
                self._validate_target(user_id=user_id, course_id=course_id, knowledge_node_id=knowledge_node_id)
                rows = self.evidence_repository.list_for_current_node(
                    user_id=user_id,
                    course_id=course_id,
                    knowledge_node_id=knowledge_node_id,
                )
                try:
                    evidence = [MasteryEvidenceSchema.model_validate(row) for row in rows]
                except ValidationError as error:
                    raise MasteryServiceError(
                        "INVALID_EVIDENCE",
                        "Persisted evidence failed the mastery input contract.",
                    ) from error
                self._validate_ownership_and_mapping(
                    evidence,
                    user_id=user_id,
                    course_id=course_id,
                    knowledge_node_id=knowledge_node_id,
                )
                knowledge_model_version = self._compatible_knowledge_model_version(evidence)
                prepared = self.calculator.prepare(evidence)
                fingerprint = calculate_evidence_fingerprint(prepared, self.calculator)
                existing = self.state_repository.get(
                    user_id=user_id,
                    course_id=course_id,
                    knowledge_node_id=knowledge_node_id,
                )
                if (
                    existing is not None
                    and existing.evidence_fingerprint == fingerprint
                    and existing.algorithm_version == self.config.algorithm_version
                ):
                    return KnowledgeStateRefreshResultSchema(
                        state=StudentKnowledgeStateSchema.model_validate(existing),
                        updated=False,
                    )

                mastery = self.calculator.calculate(prepared)
                confidence = self.confidence_estimator.estimate(prepared)
                state = existing or StudentKnowledgeState(
                    user_id=user_id,
                    course_id=course_id,
                    knowledge_node_id=knowledge_node_id,
                )
                state.knowledge_model_version = knowledge_model_version
                state.mastery_score = mastery.mastery_score
                state.mastery_status = mastery.mastery_status
                state.confidence_level = confidence.confidence_level
                state.confidence_reason_codes = [code.value for code in confidence.confidence_reason_codes]
                state.evidence_count = mastery.evidence_count
                state.independent_evidence_count = mastery.independent_evidence_count
                state.assessment_count = mastery.assessment_count
                state.algorithm_version = self.config.algorithm_version
                state.evidence_fingerprint = fingerprint
                state.calculated_at = self.clock()
                self.state_repository.save(state)
                return KnowledgeStateRefreshResultSchema(
                    state=StudentKnowledgeStateSchema.model_validate(state),
                    updated=True,
                )
        except MasteryServiceError, MasteryCalculationError:
            raise
        except (SQLAlchemyError, RuntimeError) as error:
            raise MasteryServiceError(
                "STATE_PERSISTENCE_FAILED",
                "Student knowledge state could not be persisted.",
            ) from error

    def _validate_target(self, *, user_id: int, course_id: int, knowledge_node_id: int) -> None:
        course = self.session.get(Course, course_id)
        if course is None or course.owner_id != user_id:
            raise MasteryServiceError(
                "TARGET_OWNERSHIP_MISMATCH",
                "The course does not belong to the requested user.",
            )
        node = self.session.get(KnowledgeNode, knowledge_node_id)
        if node is None or node.course_id != course_id or not node.is_active:
            raise MasteryServiceError(
                "INVALID_KNOWLEDGE_NODE",
                "The target must be an active knowledge node in the requested course.",
            )

    @staticmethod
    def _validate_ownership_and_mapping(
        evidence: list[MasteryEvidenceSchema],
        *,
        user_id: int,
        course_id: int,
        knowledge_node_id: int,
    ) -> None:
        for item in evidence:
            if item.user_id != user_id or item.course_id != course_id:
                raise MasteryServiceError(
                    "EVIDENCE_OWNERSHIP_MISMATCH",
                    "Evidence ownership does not match the target.",
                )
            if (
                item.current_knowledge_node_id != knowledge_node_id
                or item.historical_knowledge_node_ref != knowledge_node_id
            ):
                raise MasteryServiceError(
                    "INVALID_KNOWLEDGE_REFERENCE",
                    "Evidence is not explicitly mapped to the target knowledge node.",
                )

    @staticmethod
    def _compatible_knowledge_model_version(evidence: list[MasteryEvidenceSchema]) -> str | None:
        versions = {item.knowledge_model_version for item in evidence}
        if len(versions) > 1:
            raise MasteryServiceError(
                "INCOMPATIBLE_KNOWLEDGE_MODEL_VERSIONS",
                "Evidence spans incompatible knowledge model versions.",
            )
        return next(iter(versions), None)


__all__ = ["MasteryService", "MasteryServiceError"]
