from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from heapq import heapify, heappop, heappush

from backend.app.models import (
    CandidateEligibilityStatus,
    ConfidenceLevel,
    DataAvailability,
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
    CandidateNode,
    PrerequisiteEvidence,
    PriorityBreakdown,
    RecommendationContext,
    RecommendationMasteryState,
    RecommendationResult,
)
from backend.app.services.recommendation_config import (
    RECOMMENDATION_V1_CONFIG,
    RecommendationAlgorithmConfig,
)


@dataclass(frozen=True)
class _Resolution:
    frontier: frozenset[int]
    evidence: tuple[PrerequisiteEvidence, ...]
    required_assessment: frozenset[int]
    invalid: bool
    blocked: bool


@dataclass(frozen=True)
class _Graph:
    incoming: dict[int, tuple[int, ...]]
    outgoing: dict[int, tuple[int, ...]]
    invalid_nodes: frozenset[int]
    has_issues: bool


class RecommendationEngine:
    """Deterministic, side-effect-free M6-2 recommendation calculation."""

    def __init__(self, config: RecommendationAlgorithmConfig = RECOMMENDATION_V1_CONFIG) -> None:
        self.config = config

    def recommend(self, context: RecommendationContext) -> RecommendationResult:
        personalized = self._recommend_personalized(context)
        if personalized.availability_status in (
            RecommendationAvailabilityStatus.ALL_MASTERED,
            RecommendationAvailabilityStatus.INVALID_CONTEXT,
        ):
            return personalized

        plan_level = self._plan_level(context, personalized)
        if plan_level == LearningPlanLevel.PERSONALIZED:
            return personalized.model_copy(update={"plan_level": plan_level})
        if personalized.availability_status == RecommendationAvailabilityStatus.AVAILABLE:
            assessment_nodes = self._untrusted_node_ids(context)
            reasons = list(personalized.reason_codes)
            if RecommendationReasonCode.INSUFFICIENT_EVIDENCE not in reasons:
                reasons.append(RecommendationReasonCode.INSUFFICIENT_EVIDENCE)
            return personalized.model_copy(
                update={
                    "plan_level": plan_level,
                    "reason_codes": reasons,
                    "required_assessment_node_ids": sorted(
                        set(personalized.required_assessment_node_ids) | assessment_nodes
                    ),
                    "limited_by_confidence": True,
                }
            )
        return self._recommend_structural(context, plan_level)

    def _recommend_personalized(self, context: RecommendationContext) -> RecommendationResult:
        nodes = {item.knowledge_node_id: item for item in context.knowledge_nodes}
        states = {item.knowledge_node_id: item for item in context.mastery_states}
        candidates = {item.knowledge_node_id: item for item in context.candidates}
        graph = self._prepare_graph(context)
        eligible_roots = sorted(
            node_id
            for node_id, candidate in candidates.items()
            if (
                candidate.eligibility_status == CandidateEligibilityStatus.ELIGIBLE
                or self._is_review_candidate(context, node_id, candidate)
            )
            and node_id not in graph.invalid_nodes
        )
        scorable_ids = set(eligible_roots)

        if not eligible_roots:
            return self._no_root_result(context, candidates, graph)

        memo: dict[int, _Resolution] = {}

        def resolve(node_id: int) -> _Resolution:
            cached = memo.get(node_id)
            if cached is not None:
                return cached
            if node_id in graph.invalid_nodes or node_id not in nodes:
                result = _Resolution(frozenset(), (), frozenset(), True, True)
                memo[node_id] = result
                return result

            frontier: set[int] = set()
            evidence: list[PrerequisiteEvidence] = []
            required_assessment: set[int] = set()
            invalid = False
            blocked = False
            for prerequisite_id in graph.incoming.get(node_id, ()):
                status = self._prerequisite_status(states.get(prerequisite_id), prerequisite_id in graph.invalid_nodes)
                evidence.append(
                    PrerequisiteEvidence(
                        source_node_id=prerequisite_id,
                        target_node_id=node_id,
                        status=status,
                    )
                )
                if status == PrerequisiteEvidenceStatus.SATISFIED:
                    continue
                blocked = True
                if status == PrerequisiteEvidenceStatus.INSUFFICIENT_EVIDENCE:
                    required_assessment.add(prerequisite_id)
                    continue
                if status == PrerequisiteEvidenceStatus.INVALID:
                    invalid = True
                    continue
                prerequisite_resolution = resolve(prerequisite_id)
                frontier.update(prerequisite_resolution.frontier)
                evidence.extend(prerequisite_resolution.evidence)
                required_assessment.update(prerequisite_resolution.required_assessment)
                invalid = invalid or prerequisite_resolution.invalid

            if not blocked:
                candidate = candidates.get(node_id)
                if candidate is not None and (
                    candidate.eligibility_status == CandidateEligibilityStatus.ELIGIBLE or node_id in scorable_ids
                ):
                    frontier.add(node_id)
                elif self._needs_assessment(states.get(node_id)):
                    required_assessment.add(node_id)
                else:
                    invalid = True

            result = _Resolution(
                frontier=frozenset(frontier),
                evidence=self._deduplicate_evidence(evidence),
                required_assessment=frozenset(required_assessment),
                invalid=invalid,
                blocked=blocked,
            )
            memo[node_id] = result
            return result

        frontier_targets: dict[int, set[int]] = {}
        frontier_evidence: dict[int, list[PrerequisiteEvidence]] = {}
        frontier_assessments: dict[int, set[int]] = {}
        all_required_assessments: set[int] = set()
        invalid_roots: set[int] = set()
        for root_id in eligible_roots:
            resolution = resolve(root_id)
            all_required_assessments.update(resolution.required_assessment)
            if resolution.invalid:
                invalid_roots.add(root_id)
            for frontier_id in sorted(resolution.frontier):
                frontier_targets.setdefault(frontier_id, set())
                if frontier_id != root_id or resolution.blocked:
                    frontier_targets[frontier_id].add(root_id)
                frontier_evidence.setdefault(frontier_id, []).extend(resolution.evidence)
                frontier_assessments.setdefault(frontier_id, set()).update(resolution.required_assessment)

        if not frontier_targets:
            status = (
                RecommendationAvailabilityStatus.NEEDS_PREREQUISITE_ASSESSMENT
                if all_required_assessments
                else RecommendationAvailabilityStatus.INVALID_CONTEXT
            )
            reasons = (
                [RecommendationReasonCode.INSUFFICIENT_EVIDENCE]
                if all_required_assessments
                else [RecommendationReasonCode.INVALID_PREREQUISITE_GRAPH]
            )
            if graph.has_issues and RecommendationReasonCode.INVALID_PREREQUISITE_GRAPH not in reasons:
                reasons.append(RecommendationReasonCode.INVALID_PREREQUISITE_GRAPH)
            return self._unavailable_result(
                context,
                availability=status,
                reasons=reasons,
                prerequisite_status=(
                    PrerequisiteEvaluationStatus.UNSATISFIED
                    if all_required_assessments
                    else PrerequisiteEvaluationStatus.INVALID
                ),
                required_assessment=all_required_assessments,
                invalid_nodes=set(graph.invalid_nodes) | invalid_roots,
                limited_by_confidence=bool(all_required_assessments),
            )

        scored = {
            node_id: self._score(
                context=context,
                node_id=node_id,
                graph=graph,
                state=states[node_id],
            )
            for node_id in frontier_targets
        }
        selected_id = min(
            frontier_targets,
            key=lambda node_id: (
                -scored[node_id].total_priority,
                -self._importance_rank(nodes[node_id].importance),
                node_id,
            ),
        )
        breakdown = scored[selected_id]
        blocked_targets = sorted(frontier_targets[selected_id])
        required_assessment = sorted(frontier_assessments[selected_id])
        reasons = self._reason_codes(
            context=context,
            node_id=selected_id,
            state=states[selected_id],
            breakdown=breakdown,
            blocked_targets=blocked_targets,
            required_assessment=required_assessment,
            has_invalid_graph=graph.has_issues,
        )
        return RecommendationResult(
            user_id=context.user_id,
            course_id=context.course_id,
            recommended_node_id=selected_id,
            priority_breakdown=breakdown,
            reason_codes=reasons,
            prerequisite_status=(
                PrerequisiteEvaluationStatus.UNSATISFIED if blocked_targets else PrerequisiteEvaluationStatus.SATISFIED
            ),
            availability_status=RecommendationAvailabilityStatus.AVAILABLE,
            plan_level=LearningPlanLevel.PERSONALIZED,
            prerequisite_evidence=self._deduplicate_evidence(frontier_evidence[selected_id]),
            blocked_target_node_ids=blocked_targets,
            required_assessment_node_ids=required_assessment,
            excluded_invalid_node_ids=sorted(set(graph.invalid_nodes) | invalid_roots),
            limited_by_confidence=bool(required_assessment),
        )

    def _plan_level(
        self,
        context: RecommendationContext,
        personalized: RecommendationResult,
    ) -> LearningPlanLevel:
        if context.needs_initial_diagnostic:
            return LearningPlanLevel.FOUNDATIONAL
        trusted_count = len(context.knowledge_nodes) - len(self._untrusted_node_ids(context))
        trusted_coverage = Decimal(trusted_count) / Decimal(max(len(context.knowledge_nodes), 1))
        if (
            personalized.availability_status == RecommendationAvailabilityStatus.AVAILABLE
            and trusted_coverage >= self.config.personalized_min_trusted_coverage
        ):
            return LearningPlanLevel.PERSONALIZED
        return LearningPlanLevel.PRELIMINARY

    def _recommend_structural(
        self,
        context: RecommendationContext,
        plan_level: LearningPlanLevel,
    ) -> RecommendationResult:
        nodes = {item.knowledge_node_id: item for item in context.knowledge_nodes}
        states = {item.knowledge_node_id: item for item in context.mastery_states}
        graph = self._prepare_graph(context)
        valid_node_ids = set(nodes) - set(graph.invalid_nodes)
        if not valid_node_ids:
            return self._unavailable_result(
                context,
                availability=RecommendationAvailabilityStatus.INVALID_CONTEXT,
                reasons=[RecommendationReasonCode.INVALID_PREREQUISITE_GRAPH],
                prerequisite_status=PrerequisiteEvaluationStatus.INVALID,
                invalid_nodes=set(graph.invalid_nodes),
            )

        if plan_level == LearningPlanLevel.PRELIMINARY:
            evidence_by_node = {item.knowledge_node_id: item.evidence_count for item in context.evidence_metadata}
            preferred_targets = {
                node_id
                for node_id in valid_node_ids
                if evidence_by_node.get(node_id, 0) > 0
                or states[node_id].calculation_state == KnowledgeStateAvailability.CALCULATED
            }
        else:
            preferred_targets = set(valid_node_ids)
        if not preferred_targets:
            preferred_targets = set(valid_node_ids)

        memo: dict[int, _Resolution] = {}

        def resolve(node_id: int) -> _Resolution:
            cached = memo.get(node_id)
            if cached is not None:
                return cached
            if node_id not in valid_node_ids:
                result = _Resolution(frozenset(), (), frozenset(), True, True)
                memo[node_id] = result
                return result
            frontier: set[int] = set()
            evidence: list[PrerequisiteEvidence] = []
            required_assessment: set[int] = set()
            blocked = False
            invalid = False
            for prerequisite_id in graph.incoming.get(node_id, ()):
                status = self._prerequisite_status(states.get(prerequisite_id), False)
                evidence.append(
                    PrerequisiteEvidence(
                        source_node_id=prerequisite_id,
                        target_node_id=node_id,
                        status=status,
                    )
                )
                if status == PrerequisiteEvidenceStatus.SATISFIED:
                    continue
                blocked = True
                prerequisite_resolution = resolve(prerequisite_id)
                frontier.update(prerequisite_resolution.frontier)
                evidence.extend(prerequisite_resolution.evidence)
                required_assessment.update(prerequisite_resolution.required_assessment)
                invalid = invalid or prerequisite_resolution.invalid
            if not blocked:
                frontier.add(node_id)
                if self._needs_assessment(states.get(node_id)):
                    required_assessment.add(node_id)
            result = _Resolution(
                frontier=frozenset(frontier),
                evidence=self._deduplicate_evidence(evidence),
                required_assessment=frozenset(required_assessment),
                invalid=invalid,
                blocked=blocked,
            )
            memo[node_id] = result
            return result

        frontier_targets: dict[int, set[int]] = {}
        frontier_evidence: dict[int, list[PrerequisiteEvidence]] = {}
        frontier_assessments: dict[int, set[int]] = {}
        invalid_targets: set[int] = set()
        for target_id in sorted(preferred_targets):
            resolution = resolve(target_id)
            if resolution.invalid:
                invalid_targets.add(target_id)
            for frontier_id in sorted(resolution.frontier):
                frontier_targets.setdefault(frontier_id, set())
                if frontier_id != target_id or resolution.blocked:
                    frontier_targets[frontier_id].add(target_id)
                frontier_evidence.setdefault(frontier_id, []).extend(resolution.evidence)
                frontier_assessments.setdefault(frontier_id, set()).update(resolution.required_assessment)

        if not frontier_targets:
            return self._unavailable_result(
                context,
                availability=RecommendationAvailabilityStatus.INVALID_CONTEXT,
                reasons=[RecommendationReasonCode.INVALID_PREREQUISITE_GRAPH],
                prerequisite_status=PrerequisiteEvaluationStatus.INVALID,
                invalid_nodes=set(graph.invalid_nodes) | invalid_targets,
            )

        structural_scores = {
            node_id: self._structural_priority(context, node_id, graph) for node_id in frontier_targets
        }
        selected_id = min(
            frontier_targets,
            key=lambda node_id: (
                -self._preliminary_need_rank(states[node_id], plan_level),
                -structural_scores[node_id],
                -self._importance_rank(nodes[node_id].importance),
                node_id,
            ),
        )
        blocked_targets = sorted(frontier_targets[selected_id])
        required_assessment = sorted(frontier_assessments[selected_id])
        reasons = [RecommendationReasonCode.INSUFFICIENT_EVIDENCE]
        if blocked_targets:
            reasons.append(RecommendationReasonCode.PREREQUISITE_GAP)
        if structural_scores[selected_id] > 0:
            reasons.append(RecommendationReasonCode.PREREQUISITE_FOR_OTHER_NODES)
        if graph.has_issues:
            reasons.append(RecommendationReasonCode.INVALID_PREREQUISITE_GRAPH)
        return RecommendationResult(
            user_id=context.user_id,
            course_id=context.course_id,
            recommended_node_id=selected_id,
            priority_breakdown=PriorityBreakdown(
                dependency_importance=structural_scores[selected_id],
                total_priority=structural_scores[selected_id],
            ),
            reason_codes=reasons,
            prerequisite_status=(
                PrerequisiteEvaluationStatus.UNSATISFIED if blocked_targets else PrerequisiteEvaluationStatus.SATISFIED
            ),
            availability_status=RecommendationAvailabilityStatus.AVAILABLE,
            plan_level=plan_level,
            prerequisite_evidence=self._deduplicate_evidence(frontier_evidence[selected_id]),
            blocked_target_node_ids=blocked_targets,
            required_assessment_node_ids=required_assessment,
            excluded_invalid_node_ids=sorted(set(graph.invalid_nodes) | invalid_targets),
            limited_by_confidence=True,
        )

    def _structural_priority(self, context: RecommendationContext, node_id: int, graph: _Graph) -> Decimal:
        descendant_count = len(self._descendants(node_id, graph.outgoing))
        return (Decimal(descendant_count) / Decimal(max(len(context.knowledge_nodes) - 1, 1))).quantize(
            self.config.score_quantum,
            rounding=ROUND_HALF_UP,
        )

    @staticmethod
    def _preliminary_need_rank(
        state: RecommendationMasteryState,
        plan_level: LearningPlanLevel,
    ) -> int:
        if plan_level != LearningPlanLevel.PRELIMINARY or state.mastery_score is None:
            return 0
        return {
            MasteryStatus.NOT_ASSESSED: 0,
            MasteryStatus.GOOD_PERFORMANCE: 0,
            MasteryStatus.NEEDS_REINFORCEMENT: 1,
            MasteryStatus.POSSIBLY_WEAK: 2,
            MasteryStatus.NEEDS_ATTENTION: 3,
        }[state.mastery_status]

    @staticmethod
    def _untrusted_node_ids(context: RecommendationContext) -> set[int]:
        return {
            state.knowledge_node_id
            for state in context.mastery_states
            if (
                state.calculation_state != KnowledgeStateAvailability.CALCULATED
                or state.mastery_score is None
                or state.confidence_level in (ConfidenceLevel.INSUFFICIENT, ConfidenceLevel.LOW)
            )
        }

    def _score(
        self,
        *,
        context: RecommendationContext,
        node_id: int,
        graph: _Graph,
        state: RecommendationMasteryState,
    ) -> PriorityBreakdown:
        if (
            state.calculation_state != KnowledgeStateAvailability.CALCULATED
            or state.mastery_score is None
            or state.confidence_level not in (ConfidenceLevel.MEDIUM, ConfidenceLevel.HIGH)
        ):
            raise ValueError("Only trustworthy calculated mastery can be scored.")
        knowledge_gap = Decimal("1") - state.mastery_score / Decimal("100")
        descendant_count = len(self._descendants(node_id, graph.outgoing))
        dependency_importance = Decimal(descendant_count) / Decimal(max(len(context.knowledge_nodes) - 1, 1))
        if (
            context.course_importance_availability == DataAvailability.AVAILABLE
            and context.course_importance is not None
        ):
            course_importance = context.course_importance
        else:
            course_importance = self.config.neutral_missing_component
        review_by_node = {item.knowledge_node_id: item.review_risk for item in context.review_risk_states}
        if context.review_risk_availability == DataAvailability.AVAILABLE and node_id in review_by_node:
            review_risk = review_by_node[node_id]
        else:
            review_risk = self.config.neutral_missing_component
        components = (knowledge_gap, dependency_importance, course_importance, review_risk)
        if any(not value.is_finite() or value < 0 or value > 1 for value in components):
            raise ValueError("Recommendation score components must be finite values in [0, 1].")
        total = (
            self.config.knowledge_gap_weight * knowledge_gap
            + self.config.dependency_importance_weight * dependency_importance
            + self.config.course_importance_weight * course_importance
            + self.config.review_risk_weight * review_risk
        ).quantize(self.config.score_quantum, rounding=ROUND_HALF_UP)
        return PriorityBreakdown(
            knowledge_gap=knowledge_gap.quantize(self.config.score_quantum, rounding=ROUND_HALF_UP),
            dependency_importance=dependency_importance.quantize(
                self.config.score_quantum,
                rounding=ROUND_HALF_UP,
            ),
            course_importance=course_importance.quantize(self.config.score_quantum, rounding=ROUND_HALF_UP),
            review_risk=review_risk.quantize(self.config.score_quantum, rounding=ROUND_HALF_UP),
            total_priority=total,
        )

    def _prepare_graph(self, context: RecommendationContext) -> _Graph:
        node_ids = {item.knowledge_node_id for item in context.knowledge_nodes}
        invalid_nodes: set[int] = set()
        has_issues = False
        pairs: set[tuple[int, int]] = set()
        for edge in context.prerequisite_edges:
            if edge.source_node_id not in node_ids or edge.target_node_id not in node_ids:
                has_issues = True
                if edge.source_node_id not in node_ids and edge.target_node_id in node_ids:
                    invalid_nodes.add(edge.target_node_id)
                continue
            if edge.source_node_id == edge.target_node_id:
                has_issues = True
                invalid_nodes.add(edge.source_node_id)
                continue
            pairs.add((edge.source_node_id, edge.target_node_id))

        active_nodes = node_ids - invalid_nodes
        indegree = {node_id: 0 for node_id in active_nodes}
        outgoing_sets: dict[int, set[int]] = {node_id: set() for node_id in active_nodes}
        for source_id, target_id in pairs:
            if source_id in active_nodes and target_id in active_nodes:
                outgoing_sets[source_id].add(target_id)
                indegree[target_id] += 1
        ready = [node_id for node_id, count in indegree.items() if count == 0]
        heapify(ready)
        visited: set[int] = set()
        while ready:
            node_id = heappop(ready)
            visited.add(node_id)
            for target_id in sorted(outgoing_sets[node_id]):
                indegree[target_id] -= 1
                if indegree[target_id] == 0:
                    heappush(ready, target_id)
        cyclic_or_dependent = active_nodes - visited
        if cyclic_or_dependent:
            has_issues = True
            invalid_nodes.update(cyclic_or_dependent)

        incoming: dict[int, list[int]] = {node_id: [] for node_id in node_ids - invalid_nodes}
        outgoing: dict[int, list[int]] = {node_id: [] for node_id in node_ids - invalid_nodes}
        for source_id, target_id in sorted(pairs):
            if source_id not in invalid_nodes and target_id not in invalid_nodes:
                incoming[target_id].append(source_id)
                outgoing[source_id].append(target_id)
        return _Graph(
            incoming={node_id: tuple(values) for node_id, values in incoming.items()},
            outgoing={node_id: tuple(values) for node_id, values in outgoing.items()},
            invalid_nodes=frozenset(invalid_nodes),
            has_issues=has_issues,
        )

    def _prerequisite_status(
        self,
        state: RecommendationMasteryState | None,
        invalid: bool,
    ) -> PrerequisiteEvidenceStatus:
        if invalid or state is None:
            return PrerequisiteEvidenceStatus.INVALID
        if self._needs_assessment(state):
            return PrerequisiteEvidenceStatus.INSUFFICIENT_EVIDENCE
        if state.mastery_score >= self.config.prerequisite_mastery_threshold:
            return PrerequisiteEvidenceStatus.SATISFIED
        return PrerequisiteEvidenceStatus.UNSATISFIED

    @staticmethod
    def _needs_assessment(state: RecommendationMasteryState | None) -> bool:
        return (
            state is None
            or state.calculation_state != KnowledgeStateAvailability.CALCULATED
            or state.mastery_score is None
            or state.confidence_level in (ConfidenceLevel.INSUFFICIENT, ConfidenceLevel.LOW)
        )

    @staticmethod
    def _descendants(node_id: int, outgoing: dict[int, tuple[int, ...]]) -> set[int]:
        descendants: set[int] = set()
        pending = list(outgoing.get(node_id, ()))
        while pending:
            current = pending.pop()
            if current in descendants:
                continue
            descendants.add(current)
            pending.extend(outgoing.get(current, ()))
        return descendants

    def _reason_codes(
        self,
        *,
        context: RecommendationContext,
        node_id: int,
        state: RecommendationMasteryState,
        breakdown: PriorityBreakdown,
        blocked_targets: list[int],
        required_assessment: list[int],
        has_invalid_graph: bool,
    ) -> list[RecommendationReasonCode]:
        reasons = [RecommendationReasonCode.KNOWLEDGE_GAP]
        if state.mastery_score < self.config.low_mastery_threshold:
            reasons.append(RecommendationReasonCode.LOW_MASTERY)
        if blocked_targets:
            reasons.append(RecommendationReasonCode.PREREQUISITE_GAP)
        if breakdown.dependency_importance > 0:
            reasons.append(RecommendationReasonCode.PREREQUISITE_FOR_OTHER_NODES)
        if context.course_importance_availability == DataAvailability.AVAILABLE:
            if breakdown.course_importance >= self.config.high_course_importance_threshold:
                reasons.append(RecommendationReasonCode.HIGH_COURSE_IMPORTANCE)
        else:
            reasons.append(RecommendationReasonCode.NEUTRAL_COURSE_IMPORTANCE)
        review_ids = {item.knowledge_node_id for item in context.review_risk_states}
        if context.review_risk_availability == DataAvailability.AVAILABLE and node_id in review_ids:
            if breakdown.review_risk >= self.config.review_needed_threshold:
                reasons.append(RecommendationReasonCode.REVIEW_NEEDED)
        else:
            reasons.append(RecommendationReasonCode.NEUTRAL_REVIEW_RISK)
        if required_assessment:
            reasons.append(RecommendationReasonCode.INSUFFICIENT_EVIDENCE)
        if has_invalid_graph:
            reasons.append(RecommendationReasonCode.INVALID_PREREQUISITE_GRAPH)
        return reasons

    def _is_review_candidate(
        self,
        context: RecommendationContext,
        node_id: int,
        candidate: CandidateNode,
    ) -> bool:
        if (
            candidate.eligibility_status != CandidateEligibilityStatus.MASTERED
            or context.review_risk_availability != DataAvailability.AVAILABLE
        ):
            return False
        risk_by_node = {item.knowledge_node_id: item.review_risk for item in context.review_risk_states}
        return risk_by_node.get(node_id, Decimal("0")) >= self.config.review_needed_threshold

    def _no_root_result(
        self,
        context: RecommendationContext,
        candidates: dict[int, CandidateNode],
        graph: _Graph,
    ) -> RecommendationResult:
        statuses = {item.eligibility_status for item in candidates.values()}
        if graph.invalid_nodes and all(node_id in graph.invalid_nodes for node_id in candidates):
            return self._unavailable_result(
                context,
                availability=RecommendationAvailabilityStatus.INVALID_CONTEXT,
                reasons=[RecommendationReasonCode.INVALID_PREREQUISITE_GRAPH],
                prerequisite_status=PrerequisiteEvaluationStatus.INVALID,
                invalid_nodes=set(graph.invalid_nodes),
            )
        if statuses and statuses == {CandidateEligibilityStatus.MASTERED}:
            reasons = [RecommendationReasonCode.ALL_MASTERED]
            if graph.has_issues:
                reasons.append(RecommendationReasonCode.INVALID_PREREQUISITE_GRAPH)
            return self._unavailable_result(
                context,
                availability=RecommendationAvailabilityStatus.ALL_MASTERED,
                reasons=reasons,
                prerequisite_status=(
                    PrerequisiteEvaluationStatus.INVALID if graph.has_issues else PrerequisiteEvaluationStatus.SATISFIED
                ),
                invalid_nodes=set(graph.invalid_nodes),
            )
        if context.needs_initial_diagnostic:
            return self._unavailable_result(
                context,
                availability=RecommendationAvailabilityStatus.NEEDS_INITIAL_DIAGNOSTIC,
                reasons=[RecommendationReasonCode.INSUFFICIENT_EVIDENCE],
                prerequisite_status=PrerequisiteEvaluationStatus.NOT_EVALUATED,
                required_assessment=set(candidates),
                invalid_nodes=set(graph.invalid_nodes),
                limited_by_confidence=True,
            )
        assessment_nodes = {
            node_id
            for node_id, candidate in candidates.items()
            if candidate.eligibility_status
            in (CandidateEligibilityStatus.UNASSESSED, CandidateEligibilityStatus.LOW_CONFIDENCE)
        }
        reasons = [
            RecommendationReasonCode.NO_ELIGIBLE_CANDIDATE,
            RecommendationReasonCode.INSUFFICIENT_EVIDENCE,
        ]
        if graph.has_issues:
            reasons.append(RecommendationReasonCode.INVALID_PREREQUISITE_GRAPH)
        return self._unavailable_result(
            context,
            availability=RecommendationAvailabilityStatus.NO_ELIGIBLE_CANDIDATE,
            reasons=reasons,
            prerequisite_status=PrerequisiteEvaluationStatus.NOT_EVALUATED,
            required_assessment=assessment_nodes,
            invalid_nodes=set(graph.invalid_nodes),
            limited_by_confidence=bool(assessment_nodes),
        )

    @staticmethod
    def _unavailable_result(
        context: RecommendationContext,
        *,
        availability: RecommendationAvailabilityStatus,
        reasons: list[RecommendationReasonCode],
        prerequisite_status: PrerequisiteEvaluationStatus,
        required_assessment: set[int] | None = None,
        invalid_nodes: set[int] | None = None,
        limited_by_confidence: bool = False,
    ) -> RecommendationResult:
        return RecommendationResult(
            user_id=context.user_id,
            course_id=context.course_id,
            recommended_node_id=None,
            priority_breakdown=PriorityBreakdown(),
            reason_codes=reasons,
            prerequisite_status=prerequisite_status,
            availability_status=availability,
            required_assessment_node_ids=sorted(required_assessment or set()),
            excluded_invalid_node_ids=sorted(invalid_nodes or set()),
            limited_by_confidence=limited_by_confidence,
        )

    @staticmethod
    def _deduplicate_evidence(
        evidence: list[PrerequisiteEvidence],
    ) -> tuple[PrerequisiteEvidence, ...]:
        by_key = {(item.source_node_id, item.target_node_id, item.status.value): item for item in evidence}
        return tuple(by_key[key] for key in sorted(by_key))

    @staticmethod
    def _importance_rank(importance: KnowledgeImportance) -> int:
        return {
            KnowledgeImportance.LOW: 0,
            KnowledgeImportance.MEDIUM: 1,
            KnowledgeImportance.HIGH: 2,
        }[importance]


__all__ = ["RecommendationEngine"]
