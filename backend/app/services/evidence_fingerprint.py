from __future__ import annotations

import hashlib
import json
from decimal import Decimal

from backend.app.services.mastery_calculator import MasteryCalculator, PreparedEvidenceSet


def _decimal_text(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == 0:
        return "0"
    return format(normalized, "f")


def calculate_evidence_fingerprint(
    prepared: PreparedEvidenceSet,
    calculator: MasteryCalculator,
) -> str:
    canonical_rows = []
    for evidence in prepared.raw:
        canonical_rows.append(
            {
                "attribution_weight": _decimal_text(evidence.attribution_weight),
                "difficulty": evidence.difficulty.value,
                "effective_weight": _decimal_text(calculator.effective_weight(evidence)),
                "evidence_schema_version": evidence.evidence_schema_version,
                "historical_knowledge_node_ref": evidence.historical_knowledge_node_ref,
                "knowledge_model_version": evidence.knowledge_model_version,
                "normalized_score": _decimal_text(evidence.normalized_score),
                "source_assessment_id": evidence.source_assessment_id,
                "source_question_snapshot_id": evidence.source_question_snapshot_id,
                "source_response_id": evidence.source_response_id,
                "source_type": evidence.source_type.value,
            }
        )
    serialized = json.dumps(canonical_rows, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


__all__ = ["calculate_evidence_fingerprint"]
