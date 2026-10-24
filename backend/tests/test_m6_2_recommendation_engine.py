from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from backend.app.models import (
    ConfidenceLevel,
    ConfidenceReasonCode,
    DataAvailability,
    EvidenceSourceType,
    KnowledgeDifficulty,
    KnowledgeImportance,
    LearningPlanLevel,
    MasteryStatus,
    PrerequisiteEvaluationStatus,
    PrerequisiteEvidenceStatus,
    RecommendationAvailabilityStatus,
    RecommendationReasonCode,
)
from backend.app.schemas.mastery_api import KnowledgeStateAvailability
from backend.app.schemas.recommendation import (
    EvidenceMetadata,
    RecommendationContext,
    RecommendationKnowledgeNode,
    RecommendationMasteryState,
    RecommendationPrerequisiteEdge,
    ReviewRiskState,
)
from backend.app.services.recommendation_config import RecommendationAlgorithmConfig
from backend.app.services.recommendation_context_service import classify_candidate
from backend.app.services.recommendation_engine import RecommendationEngine


def _mastery_status(score: Decimal | None) -> MasteryStatus:
    if score is None:
        return MasteryStatus.NOT_ASSESSED
    if score >= Decimal("80"):
        return MasteryStatus.GOOD_PERFORMANCE
    if score >= Decimal("60"):
        return MasteryStatus.NEEDS_REINFORCEMENT
    if score >= Decimal("40"):
        return MasteryStatus.POSSIBLY_WEAK
    return MasteryStatus.NEEDS_ATTENTION


def _context(
    scores: dict[int, Decimal | None],
    *,
    edges: list[tuple[int, int]] | None = None,
    confidences: dict[int, ConfidenceLevel] | None = None,
    importances: dict[int, KnowledgeImportance] | None = None,
    course_importance: Decimal | None = None,
    review_risks: dict[int, Decimal] | None = None,
    course_id: int = 7,
    user_id: int = 11,
    needs_initial_diagnostic: bool | None = None,
) -> RecommendationContext:
    edges = edges or []
    confidences = confidences or {}
    importances = importances or {}
    review_risks = review_risks or {}
    nodes: list[RecommendationKnowledgeNode] = []
    states: list[RecommendationMasteryState] = []
    metadata: list[EvidenceMetadata] = []
    prerequisites_by_target: dict[int, list[int]] = {}
    for source_id, target_id in edges:
        prerequisites_by_target.setdefault(target_id, []).append(source_id)
    for node_id, score in sorted(scores.items()):
        confidence = confidences.get(
            node_id,
            ConfidenceLevel.INSUFFICIENT if score is None else ConfidenceLevel.MEDIUM,
        )
        node = RecommendationKnowledgeNode(
            knowledge_node_id=node_id,
            course_id=course_id,
            name=f"Node {node_id}",
            importance=importances.get(node_id, KnowledgeImportance.MEDIUM),
            difficulty=KnowledgeDifficulty.INTERMEDIATE,
        )
        state = RecommendationMasteryState(
            knowledge_node_id=node_id,
            mastery_score=score,
            mastery_status=_mastery_status(score),
            confidence_level=confidence,
            confidence_reason_codes=(
                [ConfidenceReasonCode.INSUFFICIENT_EVIDENCE]
                if confidence == ConfidenceLevel.INSUFFICIENT
                else [ConfidenceReasonCode.SUFFICIENT_EVIDENCE]
            ),
            evidence_count=0 if score is None else 6,
            independent_evidence_count=0 if score is None else 6,
            assessment_count=0 if score is None else 2,
            calculation_state=(
                KnowledgeStateAvailability.NOT_CALCULATED if score is None else KnowledgeStateAvailability.CALCULATED
            ),
        )
        nodes.append(node)
        states.append(state)
        metadata.append(
            EvidenceMetadata(
                knowledge_node_id=node_id,
                evidence_count=state.evidence_count,
                assessment_count=state.assessment_count,
                source_types=[] if score is None else [EvidenceSourceType.DIAGNOSTIC],
            )
        )
    candidates = [
        classify_candidate(
            course_id=course_id,
            node=node,
            state=state,
            prerequisite_ids=prerequisites_by_target.get(node.knowledge_node_id, []),
        )
        for node, state in zip(nodes, states, strict=True)
    ]
    return RecommendationContext(
        user_id=user_id,
        course_id=course_id,
        knowledge_nodes=nodes,
        prerequisite_edges=[
            RecommendationPrerequisiteEdge(source_node_id=source_id, target_node_id=target_id)
            for source_id, target_id in edges
        ],
        mastery_states=states,
        evidence_metadata=metadata,
        candidates=candidates,
        knowledge_importance_availability=DataAvailability.AVAILABLE,
        course_importance_availability=(
            DataAvailability.AVAILABLE if course_importance is not None else DataAvailability.UNAVAILABLE
        ),
        course_importance=course_importance,
        review_risk_availability=(DataAvailability.AVAILABLE if review_risks else DataAvailability.UNAVAILABLE),
        review_risk_states=[
            ReviewRiskState(knowledge_node_id=node_id, review_risk=risk)
            for node_id, risk in sorted(review_risks.items())
        ],
        needs_initial_diagnostic=(
            all(score is None for score in scores.values())
            if needs_initial_diagnostic is None
            else needs_initial_diagnostic
        ),
    )


def test_t01_unmet_prerequisite_blocks_dependent_target() -> None:
    result = RecommendationEngine().recommend(_context({1: Decimal("30"), 2: Decimal("10")}, edges=[(1, 2)]))
    assert result.recommended_node_id == 1
    assert result.blocked_target_node_ids == [2]
    assert result.prerequisite_status == PrerequisiteEvaluationStatus.UNSATISFIED
    assert result.plan_level == LearningPlanLevel.PERSONALIZED
    assert RecommendationReasonCode.PREREQUISITE_GAP in result.reason_codes
    assert PrerequisiteEvidenceStatus.UNSATISFIED in {item.status for item in result.prerequisite_evidence}


def test_t02_satisfied_prerequisite_allows_target() -> None:
    result = RecommendationEngine().recommend(_context({1: Decimal("70"), 2: Decimal("10")}, edges=[(1, 2)]))
    assert result.recommended_node_id == 2
    assert result.blocked_target_node_ids == []
    assert result.prerequisite_status == PrerequisiteEvaluationStatus.SATISFIED
    assert result.prerequisite_evidence == [
        result.prerequisite_evidence[0].model_copy(update={"status": PrerequisiteEvidenceStatus.SATISFIED})
    ]


def test_t03_four_level_chain_resolves_to_foundation() -> None:
    result = RecommendationEngine().recommend(
        _context(
            {1: Decimal("40"), 2: Decimal("30"), 3: Decimal("20"), 4: Decimal("10")},
            edges=[(1, 2), (2, 3), (3, 4)],
        )
    )
    assert result.recommended_node_id == 1
    assert result.blocked_target_node_ids == [2, 3, 4]
    assert {(item.source_node_id, item.target_node_id) for item in result.prerequisite_evidence} == {
        (1, 2),
        (2, 3),
        (3, 4),
    }


def test_t04_parallel_prerequisites_produce_multiple_legal_frontier_nodes() -> None:
    context = _context(
        {1: Decimal("20"), 2: Decimal("40"), 3: Decimal("10")},
        edges=[(1, 3), (2, 3)],
    )
    result = RecommendationEngine().recommend(context)
    assert result.recommended_node_id == 1
    assert result.blocked_target_node_ids == [3]
    statuses = {(item.source_node_id, item.target_node_id, item.status) for item in result.prerequisite_evidence}
    assert (1, 3, PrerequisiteEvidenceStatus.UNSATISFIED) in statuses
    assert (2, 3, PrerequisiteEvidenceStatus.UNSATISFIED) in statuses


def test_t05_formula_components_and_ranking_are_exact() -> None:
    result = RecommendationEngine().recommend(
        _context(
            {1: Decimal("20"), 2: Decimal("40")},
            course_importance=Decimal("0.8"),
            review_risks={1: Decimal("0.6"), 2: Decimal("0.1")},
        )
    )
    assert result.recommended_node_id == 1
    assert result.priority_breakdown.knowledge_gap == Decimal("0.8000")
    assert result.priority_breakdown.dependency_importance == Decimal("0.0000")
    assert result.priority_breakdown.course_importance == Decimal("0.8000")
    assert result.priority_breakdown.review_risk == Decimal("0.6000")
    assert result.priority_breakdown.total_priority == Decimal("0.5800")


def test_t06_priority_ties_use_importance_then_stable_id() -> None:
    engine = RecommendationEngine()
    importance_tie = engine.recommend(
        _context(
            {1: Decimal("40"), 2: Decimal("40")},
            importances={1: KnowledgeImportance.LOW, 2: KnowledgeImportance.HIGH},
        )
    )
    assert importance_tie.recommended_node_id == 2
    id_tie_context = _context({1: Decimal("40"), 2: Decimal("40")})
    assert engine.recommend(id_tie_context).recommended_node_id == 1
    assert engine.recommend(id_tie_context) == engine.recommend(id_tie_context)


def test_t07_cycle_is_excluded_without_blocking_unrelated_candidate() -> None:
    result = RecommendationEngine().recommend(
        _context(
            {1: Decimal("10"), 2: Decimal("20"), 3: Decimal("30")},
            edges=[(1, 2), (2, 1)],
        )
    )
    assert result.recommended_node_id == 3
    assert result.excluded_invalid_node_ids == [1, 2]
    assert RecommendationReasonCode.INVALID_PREREQUISITE_GRAPH in result.reason_codes

    only_cycle = RecommendationEngine().recommend(
        _context({1: Decimal("10"), 2: Decimal("20")}, edges=[(1, 2), (2, 1)])
    )
    assert only_cycle.recommended_node_id is None
    assert only_cycle.availability_status == RecommendationAvailabilityStatus.INVALID_CONTEXT
    assert only_cycle.prerequisite_status == PrerequisiteEvaluationStatus.INVALID


def test_t08_unassessed_is_not_zero_mastery_or_a_scored_candidate() -> None:
    result = RecommendationEngine().recommend(_context({1: None, 2: Decimal("50")}, needs_initial_diagnostic=False))
    assert result.recommended_node_id == 2
    assert result.priority_breakdown.knowledge_gap == Decimal("0.5000")
    assert 1 not in result.blocked_target_node_ids


def test_t09_low_confidence_prerequisite_becomes_a_preliminary_target() -> None:
    result = RecommendationEngine().recommend(
        _context(
            {1: Decimal("10"), 2: Decimal("20")},
            edges=[(1, 2)],
            confidences={1: ConfidenceLevel.LOW, 2: ConfidenceLevel.MEDIUM},
            needs_initial_diagnostic=False,
        )
    )
    assert result.recommended_node_id == 1
    assert result.availability_status == RecommendationAvailabilityStatus.AVAILABLE
    assert result.plan_level == LearningPlanLevel.PRELIMINARY
    assert result.blocked_target_node_ids == [2]
    assert result.required_assessment_node_ids == [1]
    assert result.limited_by_confidence is True
    assert RecommendationReasonCode.INSUFFICIENT_EVIDENCE in result.reason_codes


def test_t09b_partial_trusted_coverage_is_preliminary_without_treating_unknown_as_zero() -> None:
    result = RecommendationEngine().recommend(
        _context(
            {1: Decimal("35"), 2: None, 3: None},
            needs_initial_diagnostic=False,
        )
    )
    assert result.recommended_node_id == 1
    assert result.plan_level == LearningPlanLevel.PRELIMINARY
    assert result.priority_breakdown.knowledge_gap == Decimal("0.6500")
    assert result.required_assessment_node_ids == [2, 3]
    assert RecommendationReasonCode.INSUFFICIENT_EVIDENCE in result.reason_codes


def test_t09c_no_diagnosis_produces_a_foundational_prerequisite_route() -> None:
    result = RecommendationEngine().recommend(
        _context(
            {1: None, 2: None, 3: None},
            edges=[(1, 2), (2, 3)],
        )
    )
    assert result.recommended_node_id == 1
    assert result.plan_level == LearningPlanLevel.FOUNDATIONAL
    assert result.priority_breakdown.knowledge_gap is None
    assert result.priority_breakdown.dependency_importance == Decimal("1.0000")
    assert result.blocked_target_node_ids == [2, 3]
    assert result.required_assessment_node_ids == [1]


def test_t10_all_mastered_has_explicit_no_recommendation_state() -> None:
    result = RecommendationEngine().recommend(_context({1: Decimal("90"), 2: Decimal("85")}))
    assert result.recommended_node_id is None
    assert result.availability_status == RecommendationAvailabilityStatus.ALL_MASTERED
    assert result.reason_codes == [RecommendationReasonCode.ALL_MASTERED]

    review = RecommendationEngine().recommend(
        _context(
            {1: Decimal("90"), 2: Decimal("85")},
            review_risks={1: Decimal("0.9"), 2: Decimal("0.2")},
        )
    )
    assert review.recommended_node_id == 1
    assert RecommendationReasonCode.REVIEW_NEEDED in review.reason_codes


def test_t11_missing_importance_and_review_use_explained_neutral_values() -> None:
    result = RecommendationEngine().recommend(_context({1: Decimal("50")}))
    assert result.priority_breakdown.course_importance == Decimal("0.5000")
    assert result.priority_breakdown.review_risk == Decimal("0.5000")
    assert RecommendationReasonCode.NEUTRAL_COURSE_IMPORTANCE in result.reason_codes
    assert RecommendationReasonCode.NEUTRAL_REVIEW_RISK in result.reason_codes


def test_t12_scores_are_bounded_and_invalid_numeric_inputs_are_rejected() -> None:
    result = RecommendationEngine().recommend(
        _context(
            {1: Decimal("0"), 2: Decimal("79.99")},
            edges=[(1, 2)],
            course_importance=Decimal("1"),
            review_risks={1: Decimal("1"), 2: Decimal("0")},
        )
    )
    for value in result.priority_breakdown.model_dump().values():
        assert value is not None and Decimal("0") <= value <= Decimal("1")
    with pytest.raises(ValidationError):
        ReviewRiskState(knowledge_node_id=1, review_risk=Decimal("NaN"))
    with pytest.raises(ValueError):
        RecommendationAlgorithmConfig(knowledge_gap_weight=Decimal("0.51"))


def test_t13_same_context_produces_identical_result() -> None:
    context = _context(
        {1: Decimal("45"), 2: Decimal("25"), 3: Decimal("70")},
        edges=[(1, 3)],
    )
    engine = RecommendationEngine()
    first = engine.recommend(context)
    assert all(engine.recommend(context) == first for _ in range(5))


def test_t14_cross_course_candidate_is_rejected_by_context_contract() -> None:
    context = _context({1: Decimal("50")})
    invalid_candidate = context.candidates[0].model_copy(update={"course_id": 999})
    with pytest.raises(ValidationError):
        context.model_copy(update={"candidates": [invalid_candidate]}).model_dump()
        RecommendationContext.model_validate(
            {
                **context.model_dump(),
                "candidates": [invalid_candidate.model_dump()],
            }
        )


def test_t15_reason_codes_match_real_components_and_prerequisite_basis() -> None:
    result = RecommendationEngine().recommend(
        _context(
            {1: Decimal("20"), 2: Decimal("10")},
            edges=[(1, 2)],
            course_importance=Decimal("0.9"),
            review_risks={1: Decimal("0.8"), 2: Decimal("0.1")},
        )
    )
    assert result.recommended_node_id == 1
    assert {
        RecommendationReasonCode.LOW_MASTERY,
        RecommendationReasonCode.PREREQUISITE_GAP,
        RecommendationReasonCode.PREREQUISITE_FOR_OTHER_NODES,
        RecommendationReasonCode.HIGH_COURSE_IMPORTANCE,
        RecommendationReasonCode.REVIEW_NEEDED,
    }.issubset(result.reason_codes)
    assert RecommendationReasonCode.NEUTRAL_COURSE_IMPORTANCE not in result.reason_codes
    assert RecommendationReasonCode.NEUTRAL_REVIEW_RISK not in result.reason_codes


def test_t16_damaged_reference_is_explicit_and_other_candidate_remains_usable() -> None:
    context = _context({1: Decimal("20"), 2: Decimal("30")})
    damaged = context.model_copy(
        update={"prerequisite_edges": [RecommendationPrerequisiteEdge(source_node_id=999, target_node_id=1)]}
    )
    result = RecommendationEngine().recommend(damaged)
    assert result.recommended_node_id == 2
    assert result.excluded_invalid_node_ids == [1]
    assert RecommendationReasonCode.INVALID_PREREQUISITE_GRAPH in result.reason_codes
