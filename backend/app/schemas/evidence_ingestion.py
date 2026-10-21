from __future__ import annotations

from pydantic import BaseModel, Field

from backend.app.schemas.learning_evidence import LearningEvidenceCreateSchema


class EvidenceExtractionIssueSchema(BaseModel):
    code: str
    assessment_id: int = Field(gt=0)
    source_question_snapshot_id: int | None = Field(default=None, gt=0)
    message: str


class EvidenceExtractionPlanSchema(BaseModel):
    assessment_id: int = Field(gt=0)
    user_id: int = Field(gt=0)
    course_id: int = Field(gt=0)
    candidates: list[LearningEvidenceCreateSchema]
    issues: list[EvidenceExtractionIssueSchema]


class EvidenceIngestionResultSchema(BaseModel):
    assessment_id: int = Field(gt=0)
    candidates: int = Field(ge=0)
    created: int = Field(ge=0)
    skipped: int = Field(ge=0)
    unavailable_historical_nodes: int = Field(ge=0)
    dry_run: bool
    skip_reasons: dict[str, int] = Field(default_factory=dict)
    issues: list[EvidenceExtractionIssueSchema] = Field(default_factory=list)
