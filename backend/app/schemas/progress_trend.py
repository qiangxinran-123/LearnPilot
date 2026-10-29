from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class ProgressTrendPoint(BaseModel):
    recorded_at: datetime
    segment: int = Field(ge=0)
    overall_mastery: Decimal = Field(ge=0, le=100)
    evaluated_node_count: int = Field(ge=0)
    evaluable_node_count: int = Field(ge=0)
    coverage_ratio: float = Field(ge=0, le=1)


class ProgressTrend(BaseModel):
    course_id: int
    range: Literal["7d", "30d", "all"]
    points: list[ProgressTrendPoint]
    excluded_incompatible_history: bool
