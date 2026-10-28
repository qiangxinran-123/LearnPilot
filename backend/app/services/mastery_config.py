from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Mapping

from backend.app.models import EvidenceSourceType, QuestionDifficulty


@dataclass(frozen=True)
class MasteryAlgorithmConfig:
    algorithm_version: str = "mastery_v1"
    prior_mean: Decimal = Decimal("0.5")
    prior_strength: Decimal = Decimal("2.0")
    minimum_independent_evidence: int = 3
    difficulty_weights: Mapping[QuestionDifficulty, Decimal] = field(
        default_factory=lambda: {
            QuestionDifficulty.EASY: Decimal("1.0"),
            QuestionDifficulty.MEDIUM: Decimal("1.2"),
            QuestionDifficulty.HARD: Decimal("1.4"),
        }
    )
    source_weights: Mapping[EvidenceSourceType, Decimal] = field(
        default_factory=lambda: {
            EvidenceSourceType.DIAGNOSTIC: Decimal("1.0"),
            EvidenceSourceType.PRACTICE: Decimal("1.0"),
        }
    )
    high_confidence_minimum_assessments: int = 2
    high_confidence_minimum_difficulties: int = 2
    performance_variation_threshold: Decimal = Decimal("0.40")


MASTERY_V1_CONFIG = MasteryAlgorithmConfig()


__all__ = ["MASTERY_V1_CONFIG", "MasteryAlgorithmConfig"]
