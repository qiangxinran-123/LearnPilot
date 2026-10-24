from enum import StrEnum


class LearningPlanStatus(StrEnum):
    AVAILABLE = "available"
    SUPERSEDED = "superseded"


class LearningPlanAvailability(StrEnum):
    AVAILABLE = "available"
    STALE = "stale"
    NOT_AVAILABLE = "not_available"


class LearningPlanLevel(StrEnum):
    PERSONALIZED = "personalized"
    PRELIMINARY = "preliminary"
    FOUNDATIONAL = "foundational"


class LearningTaskType(StrEnum):
    CONCEPT_REVIEW = "concept_review"
    EXAMPLE_WALKTHROUGH = "example_walkthrough"
    TARGETED_PRACTICE = "targeted_practice"


__all__ = [
    "LearningPlanAvailability",
    "LearningPlanLevel",
    "LearningPlanStatus",
    "LearningTaskType",
]
