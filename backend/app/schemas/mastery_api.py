from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field

from backend.app.models import (
    ConfidenceLevel,
    ConfidenceReasonCode,
    EvidenceSourceType,
    MasteryStatus,
    QuestionDifficulty,
)


class KnowledgeStateAvailability(StrEnum):
    """Availability of persisted state, separate from the mastery classification."""

    CALCULATED = "calculated"
    NOT_CALCULATED = "not_calculated"
    STALE = "stale"


class KnowledgeNodeMasteryReadSchema(BaseModel):
    knowledge_node_id: int
    mastery_score: Decimal | None
    mastery_status: MasteryStatus
    confidence_level: ConfidenceLevel
    confidence_reason_codes: list[ConfidenceReasonCode]
    evidence_count: int = Field(ge=0)
    independent_evidence_count: int = Field(ge=0)
    assessment_count: int = Field(ge=0)
    knowledge_model_version: str | None
    algorithm_version: str | None
    calculated_at: datetime | None
    calculation_state: KnowledgeStateAvailability


class CourseMasteryReadSchema(BaseModel):
    course_id: int
    nodes: list[KnowledgeNodeMasteryReadSchema]


class EvidenceSummarySchema(BaseModel):
    effective_evidence_count: int = Field(ge=0)
    independent_evidence_count: int = Field(ge=0)
    assessment_count: int = Field(ge=0)
    evidence_returned: int = Field(ge=0)


class EvidenceExplanationItemSchema(BaseModel):
    evidence_id: int
    source_type: EvidenceSourceType
    source_assessment_id: int
    source_question_reference: int
    historical_knowledge_node_reference: int
    normalized_score: Decimal = Field(ge=0, le=1)
    difficulty: QuestionDifficulty
    attribution_weight: Decimal = Field(gt=0, le=1)
    occurred_at: datetime


class KnowledgeEvidenceExplanationSchema(BaseModel):
    course_id: int
    knowledge_node_id: int
    state: KnowledgeNodeMasteryReadSchema
    summary: EvidenceSummarySchema
    evidence: list[EvidenceExplanationItemSchema]


__all__ = [
    "CourseMasteryReadSchema",
    "EvidenceExplanationItemSchema",
    "EvidenceSummarySchema",
    "KnowledgeEvidenceExplanationSchema",
    "KnowledgeNodeMasteryReadSchema",
    "KnowledgeStateAvailability",
]
