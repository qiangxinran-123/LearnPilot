from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from backend.app.models import ConfidenceLevel, ConfidenceReasonCode
from backend.app.schemas.mastery import ConfidenceResultSchema, MasteryEvidenceSchema
from backend.app.services.mastery_calculator import MasteryCalculator, PreparedEvidenceSet
from backend.app.services.mastery_config import MASTERY_V1_CONFIG, MasteryAlgorithmConfig


class ConfidenceEstimator:
    def __init__(self, config: MasteryAlgorithmConfig = MASTERY_V1_CONFIG) -> None:
        self.config = config
        self.calculator = MasteryCalculator(config)

    def estimate(self, evidence: Iterable[MasteryEvidenceSchema] | PreparedEvidenceSet) -> ConfidenceResultSchema:
        prepared = evidence if isinstance(evidence, PreparedEvidenceSet) else self.calculator.prepare(evidence)
        items = prepared.independent
        evidence_count = len(items)
        assessment_ids = {item.source_assessment_id for item in items}
        difficulties = {item.difficulty for item in items}
        reasons: list[ConfidenceReasonCode] = []

        if evidence_count < self.config.minimum_independent_evidence:
            reasons.append(ConfidenceReasonCode.INSUFFICIENT_EVIDENCE)
            if evidence_count and len(assessment_ids) == 1:
                reasons.append(ConfidenceReasonCode.SINGLE_ASSESSMENT)
            if evidence_count and len(difficulties) < self.config.high_confidence_minimum_difficulties:
                reasons.append(ConfidenceReasonCode.LIMITED_DIFFICULTY_COVERAGE)
            return ConfidenceResultSchema(
                confidence_level=ConfidenceLevel.INSUFFICIENT,
                confidence_reason_codes=reasons,
            )

        reasons.append(ConfidenceReasonCode.SUFFICIENT_EVIDENCE)
        if evidence_count <= 5:
            level = ConfidenceLevel.LOW
        elif evidence_count <= 9:
            level = ConfidenceLevel.MEDIUM
        else:
            level = ConfidenceLevel.HIGH

        if len(assessment_ids) < self.config.high_confidence_minimum_assessments:
            reasons.append(ConfidenceReasonCode.SINGLE_ASSESSMENT)
            level = self._cap_at_medium(level)
        if len(difficulties) < self.config.high_confidence_minimum_difficulties:
            reasons.append(ConfidenceReasonCode.LIMITED_DIFFICULTY_COVERAGE)
            level = self._cap_at_medium(level)
        if self._has_performance_variation(items):
            reasons.append(ConfidenceReasonCode.PERFORMANCE_VARIATION)
            level = self._cap_at_medium(level)

        return ConfidenceResultSchema(confidence_level=level, confidence_reason_codes=reasons)

    def _has_performance_variation(self, evidence: tuple[MasteryEvidenceSchema, ...]) -> bool:
        by_assessment: dict[int, list[MasteryEvidenceSchema]] = {}
        for item in evidence:
            by_assessment.setdefault(item.source_assessment_id, []).append(item)
        if len(by_assessment) < 2:
            return False

        assessment_scores: list[Decimal] = []
        for items in by_assessment.values():
            weight_sum = sum((self.calculator.effective_weight(item) for item in items), start=Decimal("0"))
            weighted_score = sum(
                (self.calculator.effective_weight(item) * item.normalized_score for item in items),
                start=Decimal("0"),
            )
            assessment_scores.append(weighted_score / weight_sum)
        return max(assessment_scores) - min(assessment_scores) > self.config.performance_variation_threshold

    @staticmethod
    def _cap_at_medium(level: ConfidenceLevel) -> ConfidenceLevel:
        if level == ConfidenceLevel.HIGH:
            return ConfidenceLevel.MEDIUM
        return level


__all__ = ["ConfidenceEstimator"]
