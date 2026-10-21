from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable

from backend.app.models import MasteryStatus
from backend.app.schemas.mastery import MasteryCalculationSchema, MasteryEvidenceSchema
from backend.app.services.mastery_config import MASTERY_V1_CONFIG, MasteryAlgorithmConfig

_SCORE_QUANTUM = Decimal("0.01")


class MasteryCalculationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class PreparedEvidenceSet:
    raw: tuple[MasteryEvidenceSchema, ...]
    independent: tuple[MasteryEvidenceSchema, ...]


class MasteryCalculator:
    def __init__(self, config: MasteryAlgorithmConfig = MASTERY_V1_CONFIG) -> None:
        self.config = config

    def effective_weight(self, evidence: MasteryEvidenceSchema) -> Decimal:
        difficulty_weight = self.config.difficulty_weights.get(evidence.difficulty)
        if difficulty_weight is None:
            raise MasteryCalculationError("UNSUPPORTED_DIFFICULTY", "Evidence difficulty is not supported.")
        source_weight = self.config.source_weights.get(evidence.source_type)
        if source_weight is None:
            raise MasteryCalculationError("UNSUPPORTED_EVIDENCE_SOURCE", "Evidence source is not supported.")
        if not Decimal("0") <= evidence.normalized_score <= Decimal("1"):
            raise MasteryCalculationError("INVALID_NORMALIZED_SCORE", "Evidence score must be in [0, 1].")
        if not Decimal("0") < evidence.attribution_weight <= Decimal("1"):
            raise MasteryCalculationError("INVALID_ATTRIBUTION_WEIGHT", "Evidence weight must be in (0, 1].")
        return difficulty_weight * source_weight * evidence.attribution_weight

    def prepare(self, evidence: Iterable[MasteryEvidenceSchema]) -> PreparedEvidenceSet:
        raw_by_identity: dict[tuple[object, ...], MasteryEvidenceSchema] = {}
        for item in evidence:
            self.effective_weight(item)
            stable_identity = self.stable_identity(item)
            existing = raw_by_identity.get(stable_identity)
            if existing is not None and self.calculation_signature(existing) != self.calculation_signature(item):
                raise MasteryCalculationError(
                    "CONFLICTING_DUPLICATE_EVIDENCE",
                    "The same evidence identity has conflicting calculation values.",
                )
            raw_by_identity[stable_identity] = item

        independent_by_identity: dict[tuple[object, ...], MasteryEvidenceSchema] = {}
        for item in sorted(raw_by_identity.values(), key=self.stable_identity):
            independent_identity = self.independent_identity(item)
            existing = independent_by_identity.get(independent_identity)
            if existing is not None and self.calculation_signature(existing) != self.calculation_signature(item):
                raise MasteryCalculationError(
                    "CONFLICTING_DUPLICATE_EVIDENCE",
                    "The same answer fact has conflicting evidence values.",
                )
            independent_by_identity[independent_identity] = item

        return PreparedEvidenceSet(
            raw=tuple(sorted(raw_by_identity.values(), key=self.stable_identity)),
            independent=tuple(sorted(independent_by_identity.values(), key=self.independent_identity)),
        )

    def calculate(self, evidence: Iterable[MasteryEvidenceSchema] | PreparedEvidenceSet) -> MasteryCalculationSchema:
        prepared = evidence if isinstance(evidence, PreparedEvidenceSet) else self.prepare(evidence)
        independent_count = len(prepared.independent)
        assessment_count = len({item.source_assessment_id for item in prepared.independent})
        if independent_count < self.config.minimum_independent_evidence:
            return MasteryCalculationSchema(
                mastery_score=None,
                mastery_status=MasteryStatus.NOT_ASSESSED,
                evidence_count=len(prepared.raw),
                independent_evidence_count=independent_count,
                assessment_count=assessment_count,
            )

        weighted_score = sum(
            (self.effective_weight(item) * item.normalized_score for item in prepared.independent),
            start=Decimal("0"),
        )
        weight_sum = sum(
            (self.effective_weight(item) for item in prepared.independent),
            start=Decimal("0"),
        )
        mastery_score = (
            Decimal("100")
            * (self.config.prior_strength * self.config.prior_mean + weighted_score)
            / (self.config.prior_strength + weight_sum)
        ).quantize(_SCORE_QUANTUM, rounding=ROUND_HALF_UP)
        return MasteryCalculationSchema(
            mastery_score=mastery_score,
            mastery_status=self.classify(mastery_score),
            evidence_count=len(prepared.raw),
            independent_evidence_count=independent_count,
            assessment_count=assessment_count,
        )

    @staticmethod
    def classify(score: Decimal) -> MasteryStatus:
        if score >= Decimal("80"):
            return MasteryStatus.GOOD_PERFORMANCE
        if score >= Decimal("60"):
            return MasteryStatus.NEEDS_REINFORCEMENT
        if score >= Decimal("40"):
            return MasteryStatus.POSSIBLY_WEAK
        return MasteryStatus.NEEDS_ATTENTION

    @staticmethod
    def stable_identity(evidence: MasteryEvidenceSchema) -> tuple[object, ...]:
        return (
            evidence.source_type.value,
            evidence.source_assessment_id,
            evidence.source_question_snapshot_id,
            evidence.source_response_id,
            evidence.historical_knowledge_node_ref,
            evidence.evidence_schema_version,
        )

    @staticmethod
    def independent_identity(evidence: MasteryEvidenceSchema) -> tuple[object, ...]:
        return (
            evidence.source_type.value,
            evidence.source_assessment_id,
            evidence.source_question_snapshot_id,
            evidence.source_response_id,
            evidence.current_knowledge_node_id,
        )

    @staticmethod
    def calculation_signature(evidence: MasteryEvidenceSchema) -> tuple[object, ...]:
        return (
            evidence.user_id,
            evidence.course_id,
            evidence.historical_knowledge_node_ref,
            evidence.current_knowledge_node_id,
            evidence.knowledge_model_version,
            evidence.normalized_score,
            evidence.difficulty.value,
            evidence.attribution_weight,
        )


__all__ = [
    "MasteryCalculationError",
    "MasteryCalculator",
    "PreparedEvidenceSet",
]
