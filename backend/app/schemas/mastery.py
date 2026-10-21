from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.models import (
    ConfidenceLevel,
    ConfidenceReasonCode,
    EvidenceSourceType,
    MasteryStatus,
    QuestionDifficulty,
)


class MasteryEvidenceSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: int = Field(gt=0)
    course_id: int = Field(gt=0)
    source_type: EvidenceSourceType
    source_assessment_id: int = Field(gt=0)
    source_question_snapshot_id: int = Field(gt=0)
    source_response_id: int = Field(gt=0)
    historical_knowledge_node_ref: int = Field(gt=0)
    current_knowledge_node_id: int = Field(gt=0)
    knowledge_model_version: str | None = Field(default=None, max_length=120)
    normalized_score: Decimal = Field(ge=0, le=1)
    difficulty: QuestionDifficulty
    attribution_weight: Decimal = Field(gt=0, le=1)
    evidence_schema_version: str = Field(min_length=1, max_length=64)


class MasteryCalculationSchema(BaseModel):
    mastery_score: Decimal | None
    mastery_status: MasteryStatus
    evidence_count: int = Field(ge=0)
    independent_evidence_count: int = Field(ge=0)
    assessment_count: int = Field(ge=0)


class ConfidenceResultSchema(BaseModel):
    confidence_level: ConfidenceLevel
    confidence_reason_codes: list[ConfidenceReasonCode]


class StudentKnowledgeStateSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    course_id: int
    knowledge_node_id: int
    knowledge_model_version: str | None
    mastery_score: Decimal | None
    mastery_status: MasteryStatus
    confidence_level: ConfidenceLevel
    confidence_reason_codes: list[str]
    evidence_count: int
    independent_evidence_count: int
    assessment_count: int
    algorithm_version: str
    evidence_fingerprint: str
    calculated_at: datetime

    @field_validator("calculated_at")
    @classmethod
    def normalize_calculated_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class KnowledgeStateRefreshResultSchema(BaseModel):
    state: StudentKnowledgeStateSchema
    updated: bool


__all__ = [
    "ConfidenceResultSchema",
    "KnowledgeStateRefreshResultSchema",
    "MasteryCalculationSchema",
    "MasteryEvidenceSchema",
    "StudentKnowledgeStateSchema",
]
