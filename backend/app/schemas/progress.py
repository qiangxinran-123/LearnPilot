from decimal import Decimal

from pydantic import BaseModel, Field

from backend.app.models import ConfidenceLevel, MasteryStatus
from backend.app.schemas.mastery_api import KnowledgeStateAvailability


class ProgressNode(BaseModel):
    node_id: int
    name: str
    parent_ids: list[int]
    mastery_score: Decimal | None
    mastery_status: MasteryStatus
    confidence_level: ConfidenceLevel
    evidence_count: int = Field(ge=0)
    calculation_state: KnowledgeStateAvailability


class ProgressKnowledge(BaseModel):
    course_id: int
    nodes: list[ProgressNode]


class ProgressOverview(BaseModel):
    course_id: int
    overall_mastery: Decimal | None
    evaluated_node_count: int = Field(ge=0)
    evaluable_node_count: int = Field(ge=0)
    coverage_ratio: float | None = Field(ge=0, le=1)
    status_counts: dict[MasteryStatus, int]
    weak_nodes: list[ProgressNode]
