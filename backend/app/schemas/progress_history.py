from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class LearningEventType(StrEnum):
    DIAGNOSIS_COMPLETED = "diagnosis_completed"
    LEARNING_SESSION_COMPLETED = "learning_session_completed"


class LearningHistoryEvent(BaseModel):
    id: str
    event_type: LearningEventType
    occurred_at: datetime
    course_id: int
    knowledge_node_id: int | None
    knowledge_node_name: str | None


class LearningHistoryPage(BaseModel):
    course_id: int
    events: list[LearningHistoryEvent]
    next_cursor: str | None
