from enum import StrEnum


class TutorMessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class TeachingStrategy(StrEnum):
    HINT = "hint"
    GUIDED_QUESTION = "guided_question"
    EXAMPLE = "example"
    STEP_BY_STEP_EXPLANATION = "step_by_step_explanation"
    FULL_EXPLANATION = "full_explanation"


__all__ = ["TeachingStrategy", "TutorMessageRole"]
