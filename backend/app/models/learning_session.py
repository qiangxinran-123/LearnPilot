from enum import StrEnum


class LearningSessionStatus(StrEnum):
    CREATED = "created"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class LearningSessionTaskPhase(StrEnum):
    CONCEPT_LEARNING = "concept_learning"
    GUIDED_EXAMPLE = "guided_example"
    ADAPTIVE_PRACTICE = "adaptive_practice"


class LearningSessionTaskStatus(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class RecommendationRefreshStatus(StrEnum):
    NOT_REQUESTED = "not_requested"
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


__all__ = [
    "LearningSessionStatus",
    "LearningSessionTaskPhase",
    "LearningSessionTaskStatus",
    "RecommendationRefreshStatus",
]
