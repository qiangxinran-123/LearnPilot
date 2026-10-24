from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from sqlalchemy.orm import Session

from backend.app.db.models import KnowledgeEdge, KnowledgeNode, LearningEvidence, StudentKnowledgeState
from backend.app.models import (
    CandidateEligibilityStatus,
    CandidateExclusionReason,
    ConfidenceLevel,
    ConfidenceReasonCode,
    DataAvailability,
    KnowledgeRelationType,
    MasteryStatus,
)
from backend.app.repositories import (
    CourseRepository,
    KnowledgeEdgeRepository,
    KnowledgeNodeRepository,
    LearningEvidenceRepository,
    StudentKnowledgeStateRepository,
)
from backend.app.schemas.mastery_api import KnowledgeStateAvailability
from backend.app.schemas.recommendation import (
    CandidateNode,
    EvidenceMetadata,
    RecommendationContext,
    RecommendationKnowledgeNode,
    RecommendationMasteryState,
    RecommendationPrerequisiteEdge,
)
from backend.app.services.knowledge_relationship_validation import (
    KnowledgeRelationshipValidationError,
    RelationshipEdgeSpec,
    validate_relationship_edges,
)
from backend.app.services.mastery_read_service import is_persisted_mastery_state_current


class RecommendationContextError(ValueError):
    def __init__(self, code: str, message: str, *, details: Iterable[str] = ()) -> None:
        super().__init__(message)
        self.code = code
        self.details = tuple(details)


def prepare_prerequisite_edges(
    *,
    course_id: int,
    node_ids: set[int],
    edges: Iterable[KnowledgeEdge],
) -> list[RecommendationPrerequisiteEdge]:
    """Filter prerequisite edges, safely deduplicate them, and validate the DAG."""

    prepared: list[RecommendationPrerequisiteEdge] = []
    seen: set[tuple[int, int]] = set()
    issues: list[str] = []
    for edge in edges:
        if edge.relation_type != KnowledgeRelationType.PREREQUISITE:
            continue
        key = (edge.source_node_id, edge.target_node_id)
        if key in seen:
            continue
        seen.add(key)
        if edge.course_id != course_id:
            issues.append(f"edge {edge.id or '<unpersisted>'}: course mismatch")
            continue
        if edge.source_node_id not in node_ids or edge.target_node_id not in node_ids:
            issues.append(f"edge {edge.id or '<unpersisted>'}: unknown or inactive node reference")
            continue
        if edge.source_node_id == edge.target_node_id:
            issues.append(f"edge {edge.id or '<unpersisted>'}: self reference")
            continue
        prepared.append(
            RecommendationPrerequisiteEdge(
                source_node_id=edge.source_node_id,
                target_node_id=edge.target_node_id,
            )
        )
    if issues:
        raise RecommendationContextError(
            "INVALID_PREREQUISITE_EDGE",
            "Prerequisite edges are invalid for the requested course.",
            details=issues,
        )
    try:
        validate_relationship_edges(
            node_ids=node_ids,
            edges=[
                RelationshipEdgeSpec(
                    source_node_id=edge.source_node_id,
                    target_node_id=edge.target_node_id,
                    relation_type=KnowledgeRelationType.PREREQUISITE,
                )
                for edge in prepared
            ],
        )
    except KnowledgeRelationshipValidationError as error:
        raise RecommendationContextError(error.code, str(error)) from error
    return sorted(prepared, key=lambda edge: (edge.source_node_id, edge.target_node_id))


def classify_candidate(
    *,
    course_id: int,
    node: RecommendationKnowledgeNode,
    state: RecommendationMasteryState,
    prerequisite_ids: Iterable[int],
) -> CandidateNode:
    """Classify basic eligibility only; no priority or prerequisite attainment is computed."""

    status: CandidateEligibilityStatus
    reason: CandidateExclusionReason | None
    if node.course_id != course_id or state.knowledge_node_id != node.knowledge_node_id:
        status, reason = CandidateEligibilityStatus.INVALID, CandidateExclusionReason.COURSE_MISMATCH
    elif state.calculation_state == KnowledgeStateAvailability.STALE:
        status, reason = CandidateEligibilityStatus.UNASSESSED, CandidateExclusionReason.STALE_MASTERY
    elif (
        state.calculation_state != KnowledgeStateAvailability.CALCULATED
        or state.mastery_status == MasteryStatus.NOT_ASSESSED
    ):
        status, reason = CandidateEligibilityStatus.UNASSESSED, CandidateExclusionReason.MISSING_MASTERY
    elif state.mastery_score is None:
        status, reason = CandidateEligibilityStatus.INVALID, CandidateExclusionReason.INVALID_STATE
    elif state.confidence_level in (ConfidenceLevel.INSUFFICIENT, ConfidenceLevel.LOW):
        status, reason = CandidateEligibilityStatus.LOW_CONFIDENCE, CandidateExclusionReason.LOW_CONFIDENCE
    elif state.mastery_status == MasteryStatus.GOOD_PERFORMANCE:
        status, reason = CandidateEligibilityStatus.MASTERED, CandidateExclusionReason.ALREADY_MASTERED
    else:
        status, reason = CandidateEligibilityStatus.ELIGIBLE, None
    return CandidateNode(
        knowledge_node_id=node.knowledge_node_id,
        course_id=node.course_id,
        mastery_state=state.mastery_status,
        mastery_score=state.mastery_score,
        confidence_state=state.confidence_level,
        prerequisite_ids=sorted(set(prerequisite_ids)),
        eligibility_status=status,
        exclusion_reason=reason,
    )


class RecommendationContextService:
    """Assemble validated M3-M5 recommendation inputs without database writes."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.courses = CourseRepository(session)
        self.nodes = KnowledgeNodeRepository(session)
        self.edges = KnowledgeEdgeRepository(session)
        self.states = StudentKnowledgeStateRepository(session)
        self.evidence = LearningEvidenceRepository(session)

    def build_recommendation_context(self, *, user_id: int, course_id: int) -> RecommendationContext:
        with self.session.begin():
            if self.courses.get_for_owner(course_id, user_id) is None:
                # Preserve the existing ownership-hiding contract used by M3-M5.
                raise RecommendationContextError("COURSE_NOT_FOUND", "Course not found.")
            node_rows = self.nodes.list_by_course(course_id)
            if not node_rows:
                raise RecommendationContextError(
                    "KNOWLEDGE_MODEL_NOT_FOUND",
                    "The course has no active knowledge model.",
                )
            node_ids = {node.id for node in node_rows}
            prerequisite_edges = prepare_prerequisite_edges(
                course_id=course_id,
                node_ids=node_ids,
                edges=self.edges.list_current_by_course(course_id),
            )
            state_by_node = {
                state.knowledge_node_id: state
                for state in self.states.list_by_course_and_user(user_id=user_id, course_id=course_id)
                if state.knowledge_node_id in node_ids
            }
            evidence_rows = self.evidence.list_submitted_for_current_nodes(
                user_id=user_id,
                course_id=course_id,
                knowledge_node_ids=sorted(node_ids),
            )
            evidence_by_node: dict[int, list[LearningEvidence]] = defaultdict(list)
            for row in evidence_rows:
                if row.current_knowledge_node_id in node_ids:
                    evidence_by_node[row.current_knowledge_node_id].append(row)

            knowledge_nodes = [self._knowledge_node(row) for row in node_rows]
            mastery_states = [
                self._mastery_state(
                    node_id=node.id,
                    state=state_by_node.get(node.id),
                    evidence=evidence_by_node[node.id],
                )
                for node in node_rows
            ]
            metadata = [self._evidence_metadata(node.id, evidence_by_node[node.id]) for node in node_rows]
            prerequisites_by_target: dict[int, list[int]] = defaultdict(list)
            for edge in prerequisite_edges:
                prerequisites_by_target[edge.target_node_id].append(edge.source_node_id)
            candidates = [
                classify_candidate(
                    course_id=course_id,
                    node=node,
                    state=state,
                    prerequisite_ids=prerequisites_by_target[node.knowledge_node_id],
                )
                for node, state in zip(knowledge_nodes, mastery_states, strict=True)
            ]
            return RecommendationContext(
                user_id=user_id,
                course_id=course_id,
                knowledge_nodes=knowledge_nodes,
                prerequisite_edges=prerequisite_edges,
                mastery_states=mastery_states,
                evidence_metadata=metadata,
                candidates=candidates,
                knowledge_importance_availability=DataAvailability.AVAILABLE,
                course_importance_availability=DataAvailability.UNAVAILABLE,
                review_risk_availability=DataAvailability.UNAVAILABLE,
                latest_valid_assessment_at=max(
                    (row.occurred_at for row in evidence_rows),
                    default=None,
                ),
                needs_initial_diagnostic=not evidence_rows,
            )

    @staticmethod
    def _knowledge_node(node: KnowledgeNode) -> RecommendationKnowledgeNode:
        return RecommendationKnowledgeNode(
            knowledge_node_id=node.id,
            course_id=node.course_id,
            name=node.name,
            importance=node.importance,
            difficulty=node.difficulty,
        )

    @staticmethod
    def _mastery_state(
        *,
        node_id: int,
        state: StudentKnowledgeState | None,
        evidence: list[LearningEvidence],
    ) -> RecommendationMasteryState:
        if state is None:
            return RecommendationContextService._unavailable_mastery(
                node_id,
                KnowledgeStateAvailability.NOT_CALCULATED,
            )
        if not is_persisted_mastery_state_current(node_id=node_id, state=state, rows=evidence):
            return RecommendationContextService._unavailable_mastery(
                node_id,
                KnowledgeStateAvailability.STALE,
                state,
            )
        return RecommendationMasteryState(
            knowledge_node_id=node_id,
            mastery_score=state.mastery_score,
            mastery_status=state.mastery_status,
            confidence_level=state.confidence_level,
            confidence_reason_codes=[ConfidenceReasonCode(item) for item in state.confidence_reason_codes],
            evidence_count=state.evidence_count,
            independent_evidence_count=state.independent_evidence_count,
            assessment_count=state.assessment_count,
            calculation_state=KnowledgeStateAvailability.CALCULATED,
            calculated_at=state.calculated_at,
        )

    @staticmethod
    def _unavailable_mastery(
        node_id: int,
        availability: KnowledgeStateAvailability,
        state: StudentKnowledgeState | None = None,
    ) -> RecommendationMasteryState:
        return RecommendationMasteryState(
            knowledge_node_id=node_id,
            mastery_score=None,
            mastery_status=MasteryStatus.NOT_ASSESSED,
            confidence_level=ConfidenceLevel.INSUFFICIENT,
            confidence_reason_codes=[ConfidenceReasonCode.INSUFFICIENT_EVIDENCE],
            evidence_count=0,
            independent_evidence_count=0,
            assessment_count=0,
            calculation_state=availability,
            calculated_at=state.calculated_at if state else None,
        )

    @staticmethod
    def _evidence_metadata(node_id: int, rows: list[LearningEvidence]) -> EvidenceMetadata:
        return EvidenceMetadata(
            knowledge_node_id=node_id,
            evidence_count=len(rows),
            assessment_count=len({row.source_assessment_id for row in rows}),
            source_types=sorted({row.source_type for row in rows}, key=lambda item: item.value),
            latest_evidence_at=max((row.occurred_at for row in rows), default=None),
        )


__all__ = [
    "RecommendationContextError",
    "RecommendationContextService",
    "classify_candidate",
    "prepare_prerequisite_edges",
]
