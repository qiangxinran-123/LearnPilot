from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from backend.app.models import (
    LearningPlanAvailability,
    LearningPlanLevel,
    LearningPlanStatus,
    LearningTaskType,
    RecommendationAvailabilityStatus,
    RecommendationReasonCode,
)
from backend.app.schemas.recommendation import PrerequisiteEvidence, PriorityBreakdown


class LearningTaskRead(BaseModel):
    task_id: int = Field(gt=0)
    knowledge_node_id: int = Field(gt=0)
    task_type: LearningTaskType
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    order_index: int = Field(ge=0, le=2)
    estimated_minutes: int | None = Field(default=None, gt=0)


class LearningPlanRead(BaseModel):
    plan_id: int = Field(gt=0)
    user_id: int = Field(gt=0)
    course_id: int = Field(gt=0)
    target_node_id: int = Field(gt=0)
    reason_codes: list[RecommendationReasonCode]
    priority_score: Decimal = Field(ge=0, le=1)
    priority_breakdown: PriorityBreakdown
    prerequisite_evidence: list[PrerequisiteEvidence]
    blocked_target_node_ids: list[int]
    status: LearningPlanStatus
    tasks: list[LearningTaskRead] = Field(min_length=1, max_length=3)
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_task_order(self) -> LearningPlanRead:
        if [task.order_index for task in self.tasks] != list(range(len(self.tasks))):
            raise ValueError("Learning tasks must use contiguous zero-based ordering.")
        if any(task.knowledge_node_id != self.target_node_id for task in self.tasks):
            raise ValueError("Learning tasks must match the plan target node.")
        if self.priority_breakdown.total_priority != self.priority_score:
            raise ValueError("Plan priority must match its recommendation breakdown.")
        return self


class LearningPlanResponse(BaseModel):
    availability: LearningPlanAvailability
    recommendation_status: RecommendationAvailabilityStatus
    plan_level: LearningPlanLevel | None = None
    plan: LearningPlanRead | None = None
    reused: bool = False

    @model_validator(mode="after")
    def validate_availability(self) -> LearningPlanResponse:
        if self.availability in (LearningPlanAvailability.AVAILABLE, LearningPlanAvailability.STALE):
            if self.plan is None:
                raise ValueError("Available or stale plan responses require a persisted plan.")
        elif self.plan is not None:
            raise ValueError("Not-available plan responses cannot expose a plan.")
        if self.reused and self.availability != LearningPlanAvailability.AVAILABLE:
            raise ValueError("Only an available plan can be reused.")
        if self.recommendation_status == RecommendationAvailabilityStatus.AVAILABLE:
            if self.plan_level is None:
                raise ValueError("Available recommendations require a plan level.")
        elif self.plan_level is not None:
            raise ValueError("Unavailable recommendations cannot expose a plan level.")
        return self


__all__ = ["LearningPlanRead", "LearningPlanResponse", "LearningTaskRead"]
