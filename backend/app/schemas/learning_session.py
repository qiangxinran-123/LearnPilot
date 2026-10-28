from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from backend.app.models import (
    LearningSessionStatus,
    LearningSessionTaskPhase,
    LearningSessionTaskStatus,
    RecommendationRefreshStatus,
)


class LearningSessionCreate(BaseModel):
    course_id: int = Field(gt=0)
    target_knowledge_node_id: int | None = Field(default=None, gt=0)
    learning_plan_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_target_source(self) -> LearningSessionCreate:
        if (self.target_knowledge_node_id is None) == (self.learning_plan_id is None):
            raise ValueError("Provide exactly one of target_knowledge_node_id or learning_plan_id.")
        return self


class LearningSessionTaskRead(BaseModel):
    task_id: int = Field(gt=0)
    phase: LearningSessionTaskPhase
    order_index: int = Field(ge=0, le=2)
    status: LearningSessionTaskStatus
    source_learning_task_id: int | None = Field(default=None, gt=0)
    progress: dict[str, str | int | bool]
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class LearningSessionRead(BaseModel):
    session_id: int = Field(gt=0)
    user_id: int = Field(gt=0)
    course_id: int = Field(gt=0)
    course_name: str = Field(min_length=1, max_length=255)
    target_knowledge_node_id: int = Field(gt=0)
    target_knowledge_node_name: str = Field(min_length=1, max_length=255)
    source_learning_plan_id: int | None = Field(default=None, gt=0)
    practice_assessment_id: int | None = Field(default=None, gt=0)
    status: LearningSessionStatus
    session_contract_version: str
    completion_summary: dict[str, object] | None
    recommendation_refresh_status: RecommendationRefreshStatus
    tasks: list[LearningSessionTaskRead] = Field(min_length=3, max_length=3)
    started_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    created_at: datetime
    updated_at: datetime
    reused: bool = False

    @model_validator(mode="after")
    def validate_task_order(self) -> LearningSessionRead:
        if [task.order_index for task in self.tasks] != [0, 1, 2]:
            raise ValueError("Session tasks must use the frozen three-phase order.")
        return self


class ActiveLearningSessionResponse(BaseModel):
    session: LearningSessionRead | None = None


class LearningSessionTaskUpdate(BaseModel):
    status: LearningSessionTaskStatus


__all__ = [
    "ActiveLearningSessionResponse",
    "LearningSessionCreate",
    "LearningSessionRead",
    "LearningSessionTaskRead",
    "LearningSessionTaskUpdate",
]
