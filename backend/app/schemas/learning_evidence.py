from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.models import EvidenceSourceType, QuestionDifficulty


class LearningEvidenceCreateSchema(BaseModel):
    user_id: int = Field(gt=0)
    course_id: int = Field(gt=0)
    source_type: EvidenceSourceType = EvidenceSourceType.DIAGNOSTIC
    source_assessment_id: int = Field(gt=0)
    source_question_snapshot_id: int = Field(gt=0)
    source_response_id: int = Field(gt=0)
    historical_knowledge_node_ref: int = Field(gt=0)
    current_knowledge_node_id: int | None = Field(default=None, gt=0)
    knowledge_model_version: str | None = Field(default=None, max_length=120)
    normalized_score: Decimal = Field(ge=0, le=1, max_digits=6, decimal_places=5)
    difficulty: QuestionDifficulty
    attribution_weight: Decimal = Field(gt=0, le=1, max_digits=6, decimal_places=5)
    source_scoring_version: str = Field(min_length=1, max_length=64)
    evidence_schema_version: str = Field(
        default="learning_evidence_v1",
        min_length=1,
        max_length=64,
        pattern=r"^learning_evidence_v[1-9][0-9]*$",
    )
    occurred_at: datetime

    @field_validator("knowledge_model_version", mode="before")
    @classmethod
    def normalize_optional_version(cls, value: object) -> object:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @field_validator("source_scoring_version", "evidence_schema_version")
    @classmethod
    def normalize_required_version(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Version must not be blank.")
        return normalized

    @field_validator("occurred_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware.")
        return value


class LearningEvidenceSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    course_id: int
    source_type: EvidenceSourceType
    source_assessment_id: int
    source_question_snapshot_id: int
    source_response_id: int
    historical_knowledge_node_ref: int
    current_knowledge_node_id: int | None
    knowledge_model_version: str | None
    normalized_score: Decimal
    difficulty: QuestionDifficulty
    attribution_weight: Decimal
    source_scoring_version: str
    evidence_schema_version: str
    occurred_at: datetime
    created_at: datetime
