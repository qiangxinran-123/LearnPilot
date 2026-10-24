from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class RecommendationAlgorithmConfig:
    algorithm_version: str = "recommendation_v1"
    knowledge_gap_weight: Decimal = Decimal("0.50")
    dependency_importance_weight: Decimal = Decimal("0.25")
    course_importance_weight: Decimal = Decimal("0.15")
    review_risk_weight: Decimal = Decimal("0.10")
    prerequisite_mastery_threshold: Decimal = Decimal("60")
    low_mastery_threshold: Decimal = Decimal("60")
    neutral_missing_component: Decimal = Decimal("0.50")
    high_course_importance_threshold: Decimal = Decimal("0.75")
    review_needed_threshold: Decimal = Decimal("0.65")
    personalized_min_trusted_coverage: Decimal = Decimal("0.50")
    score_quantum: Decimal = Decimal("0.0001")

    def __post_init__(self) -> None:
        weights = (
            self.knowledge_gap_weight,
            self.dependency_importance_weight,
            self.course_importance_weight,
            self.review_risk_weight,
        )
        if any(not value.is_finite() or value < 0 or value > 1 for value in weights):
            raise ValueError("Recommendation weights must be finite values in [0, 1].")
        if sum(weights, start=Decimal("0")) != Decimal("1"):
            raise ValueError("Recommendation weights must sum to 1.")
        for threshold in (self.prerequisite_mastery_threshold, self.low_mastery_threshold):
            if not threshold.is_finite() or threshold < 0 or threshold > 100:
                raise ValueError("Mastery thresholds must be finite values in [0, 100].")
        for value in (
            self.neutral_missing_component,
            self.high_course_importance_threshold,
            self.review_needed_threshold,
            self.personalized_min_trusted_coverage,
        ):
            if not value.is_finite() or value < 0 or value > 1:
                raise ValueError("Normalized recommendation configuration must be in [0, 1].")
        if not self.algorithm_version or not self.score_quantum.is_finite() or self.score_quantum <= 0:
            raise ValueError("Recommendation algorithm version and score quantum must be valid.")


RECOMMENDATION_V1_CONFIG = RecommendationAlgorithmConfig()


__all__ = ["RECOMMENDATION_V1_CONFIG", "RecommendationAlgorithmConfig"]
