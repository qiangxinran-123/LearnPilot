from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from backend.app.models import ConfidenceLevel, MasteryStatus
from backend.app.schemas.mastery_api import KnowledgeStateAvailability


class ReviewRiskLevel(StrEnum):
    REVIEW_DUE = "review_due"
    WATCH = "watch"
    LOW_RISK = "low_risk"
    INSUFFICIENT_DATA = "insufficient_data"


class ReviewReason(StrEnum):
    STALE_MASTERY = "stale_mastery"
    UNAVAILABLE_MASTERY = "unavailable_mastery"
    INVALID_PRACTICE_TIME = "invalid_practice_time"
    WEAK_MASTERY = "weak_mastery"
    REINFORCEMENT = "reinforcement"
    NO_PRACTICE = "no_practice"
    LOW_CONFIDENCE = "low_confidence"
    LONG_GAP = "long_gap"
    MODERATE_GAP = "moderate_gap"
    LIMITED_RECENT_PRACTICE = "limited_recent_practice"
    RECENT_PRACTICE = "recent_practice"


class ReviewRiskItem(BaseModel):
    knowledge_node_id: int
    name: str
    mastery_score: str | None
    mastery_status: MasteryStatus
    confidence_level: ConfidenceLevel
    calculation_state: KnowledgeStateAvailability
    evidence_count: int = Field(ge=0)
    risk_level: ReviewRiskLevel
    reason_code: ReviewReason
    reason_text: str
    last_practice_at: datetime | None
    days_since_practice: int | None = Field(default=None, ge=0)


class ReviewRiskResponse(BaseModel):
    course_id: int
    assessed_at: datetime
    total_node_count: int = Field(ge=0)
    counts: dict[ReviewRiskLevel, int]
    items: list[ReviewRiskItem]
