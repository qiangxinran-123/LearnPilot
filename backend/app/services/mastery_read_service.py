from __future__ import annotations

from collections import defaultdict

from fastapi import Depends
from pydantic import ValidationError
from sqlalchemy.orm import Session

from backend.app.core.settings import Settings, get_settings
from backend.app.db.models import Course, KnowledgeNode, LearningEvidence, StudentKnowledgeState
from backend.app.db.session import get_db
from backend.app.models import ConfidenceLevel, ConfidenceReasonCode, MasteryStatus
from backend.app.repositories import (
    CourseRepository,
    KnowledgeNodeRepository,
    LearningEvidenceRepository,
    StudentKnowledgeStateRepository,
    UserRepository,
)
from backend.app.schemas.mastery import MasteryEvidenceSchema
from backend.app.schemas.mastery_api import (
    CourseMasteryReadSchema,
    EvidenceExplanationItemSchema,
    EvidenceSummarySchema,
    KnowledgeEvidenceExplanationSchema,
    KnowledgeNodeMasteryReadSchema,
    KnowledgeStateAvailability,
)
from backend.app.services.evidence_fingerprint import calculate_evidence_fingerprint
from backend.app.services.mastery_calculator import MasteryCalculationError, MasteryCalculator
from backend.app.services.mastery_config import MASTERY_V1_CONFIG


class MasteryReadError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class MasteryReadService:
    """Read persisted M5-C state without triggering ingestion or recalculation."""

    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.courses = CourseRepository(session)
        self.nodes = KnowledgeNodeRepository(session)
        self.evidence = LearningEvidenceRepository(session)
        self.states = StudentKnowledgeStateRepository(session)
        self.users = UserRepository(session)
        self.calculator = MasteryCalculator(MASTERY_V1_CONFIG)

    def course_mastery(self, course_id: int) -> CourseMasteryReadSchema:
        with self.session.begin():
            owner_id = self._require_owner_id()
            self._require_course(course_id, owner_id)
            nodes = self.nodes.list_by_course(course_id)
            states = {
                state.knowledge_node_id: state
                for state in self.states.list_by_course_and_user(user_id=owner_id, course_id=course_id)
            }
            evidence_by_node = self._submitted_evidence_by_node(
                user_id=owner_id,
                course_id=course_id,
                node_ids=[node.id for node in nodes],
            )
            return CourseMasteryReadSchema(
                course_id=course_id,
                nodes=[
                    self._state_view(node.id, states.get(node.id), evidence_by_node.get(node.id, [])) for node in nodes
                ],
            )

    def node_mastery(self, course_id: int, node_id: int) -> KnowledgeNodeMasteryReadSchema:
        with self.session.begin():
            owner_id = self._require_owner_id()
            self._require_course(course_id, owner_id)
            self._require_node(course_id, node_id)
            state = self.states.get(user_id=owner_id, course_id=course_id, knowledge_node_id=node_id)
            evidence = self._submitted_evidence_by_node(
                user_id=owner_id,
                course_id=course_id,
                node_ids=[node_id],
            )[node_id]
            return self._state_view(node_id, state, evidence)

    def node_evidence(
        self,
        course_id: int,
        node_id: int,
        *,
        offset: int,
        limit: int,
    ) -> KnowledgeEvidenceExplanationSchema:
        with self.session.begin():
            owner_id = self._require_owner_id()
            self._require_course(course_id, owner_id)
            self._require_node(course_id, node_id)
            state = self.states.get(user_id=owner_id, course_id=course_id, knowledge_node_id=node_id)
            evidence = self._submitted_evidence_by_node(
                user_id=owner_id,
                course_id=course_id,
                node_ids=[node_id],
            )[node_id]
            state_view = self._state_view(node_id, state, evidence)

            # Evidence is explained only when it is exactly the persisted M5-C
            # input set.  Stale or uncalculated state must be refreshed through a
            # write-side workflow, never through this GET path.
            explainable = evidence if state_view.calculation_state == KnowledgeStateAvailability.CALCULATED else []
            page = explainable[offset : offset + limit]
            return KnowledgeEvidenceExplanationSchema(
                course_id=course_id,
                knowledge_node_id=node_id,
                state=state_view,
                summary=EvidenceSummarySchema(
                    effective_evidence_count=state_view.evidence_count,
                    independent_evidence_count=state_view.independent_evidence_count,
                    assessment_count=state_view.assessment_count,
                    evidence_returned=len(page),
                ),
                evidence=[self._evidence_item(item) for item in page],
            )

    def _require_owner_id(self) -> int:
        owner = self.users.get_by_email(self.settings.legacy_bootstrap_user)
        if owner is None:
            # Unlike older legacy services, GET must not create a bootstrap user.
            raise MasteryReadError("COURSE_NOT_FOUND", "Course not found.")
        return owner.id

    def _require_course(self, course_id: int, owner_id: int) -> Course:
        course = self.courses.get_for_owner(course_id, owner_id)
        if course is None:
            raise MasteryReadError("COURSE_NOT_FOUND", "Course not found.")
        return course

    def _require_node(self, course_id: int, node_id: int) -> KnowledgeNode:
        node = self.nodes.get_by_id(node_id)
        if node is None or node.course_id != course_id or not node.is_active:
            raise MasteryReadError("KNOWLEDGE_NODE_NOT_FOUND", "Knowledge node not found.")
        return node

    def _submitted_evidence_by_node(
        self,
        *,
        user_id: int,
        course_id: int,
        node_ids: list[int],
    ) -> dict[int, list[LearningEvidence]]:
        grouped: dict[int, list[LearningEvidence]] = defaultdict(list)
        for item in self.evidence.list_submitted_for_current_nodes(
            user_id=user_id,
            course_id=course_id,
            knowledge_node_ids=node_ids,
        ):
            if item.current_knowledge_node_id is not None:
                grouped[item.current_knowledge_node_id].append(item)
        return grouped

    def _state_view(
        self,
        node_id: int,
        state: StudentKnowledgeState | None,
        evidence: list[LearningEvidence],
    ) -> KnowledgeNodeMasteryReadSchema:
        if state is None:
            return self._unavailable_state(node_id, KnowledgeStateAvailability.NOT_CALCULATED)
        if not self._matches_persisted_input(node_id, state, evidence):
            return self._unavailable_state(node_id, KnowledgeStateAvailability.STALE, state)
        return KnowledgeNodeMasteryReadSchema(
            knowledge_node_id=node_id,
            mastery_score=state.mastery_score,
            mastery_status=state.mastery_status,
            confidence_level=state.confidence_level,
            confidence_reason_codes=[ConfidenceReasonCode(item) for item in state.confidence_reason_codes],
            evidence_count=state.evidence_count,
            independent_evidence_count=state.independent_evidence_count,
            assessment_count=state.assessment_count,
            knowledge_model_version=state.knowledge_model_version,
            algorithm_version=state.algorithm_version,
            calculated_at=state.calculated_at,
            calculation_state=KnowledgeStateAvailability.CALCULATED,
        )

    def _matches_persisted_input(
        self,
        node_id: int,
        state: StudentKnowledgeState,
        rows: list[LearningEvidence],
    ) -> bool:
        if state.algorithm_version != MASTERY_V1_CONFIG.algorithm_version:
            return False
        try:
            evidence = [MasteryEvidenceSchema.model_validate(row) for row in rows]
            for item in evidence:
                if (
                    item.user_id != state.user_id
                    or item.course_id != state.course_id
                    or item.current_knowledge_node_id != node_id
                    or item.historical_knowledge_node_ref != node_id
                ):
                    return False
            versions = {item.knowledge_model_version for item in evidence}
            if len(versions) > 1:
                return False
            prepared = self.calculator.prepare(evidence)
            return calculate_evidence_fingerprint(prepared, self.calculator) == state.evidence_fingerprint
        except MasteryCalculationError, ValidationError:
            return False

    @staticmethod
    def _unavailable_state(
        node_id: int,
        availability: KnowledgeStateAvailability,
        persisted: StudentKnowledgeState | None = None,
    ) -> KnowledgeNodeMasteryReadSchema:
        return KnowledgeNodeMasteryReadSchema(
            knowledge_node_id=node_id,
            mastery_score=None,
            mastery_status=MasteryStatus.NOT_ASSESSED,
            confidence_level=ConfidenceLevel.INSUFFICIENT,
            confidence_reason_codes=[ConfidenceReasonCode.INSUFFICIENT_EVIDENCE],
            evidence_count=0,
            independent_evidence_count=0,
            assessment_count=0,
            knowledge_model_version=persisted.knowledge_model_version if persisted else None,
            algorithm_version=persisted.algorithm_version if persisted else None,
            calculated_at=persisted.calculated_at if persisted else None,
            calculation_state=availability,
        )

    @staticmethod
    def _evidence_item(item: LearningEvidence) -> EvidenceExplanationItemSchema:
        return EvidenceExplanationItemSchema(
            evidence_id=item.id,
            source_type=item.source_type,
            source_assessment_id=item.source_assessment_id,
            source_question_reference=item.source_question_snapshot_id,
            historical_knowledge_node_reference=item.historical_knowledge_node_ref,
            normalized_score=item.normalized_score,
            difficulty=item.difficulty,
            attribution_weight=item.attribution_weight,
            occurred_at=item.occurred_at,
        )


def get_mastery_read_service(
    session: Session = Depends(get_db), settings: Settings = Depends(get_settings)
) -> MasteryReadService:
    return MasteryReadService(session, settings)


__all__ = ["MasteryReadError", "MasteryReadService", "get_mastery_read_service"]
