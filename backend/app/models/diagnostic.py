from enum import StrEnum


class QuestionType(StrEnum):
    SINGLE_CHOICE = "single_choice"
    TRUE_FALSE = "true_false"
    MULTIPLE_CHOICE = "multiple_choice"


class QuestionDifficulty(StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class QuestionValidationStatus(StrEnum):
    PENDING = "pending"
    VALIDATED = "validated"
    REJECTED = "rejected"


class KnowledgeRelationRole(StrEnum):
    PRIMARY = "primary"
    SECONDARY = "secondary"


class AssessmentType(StrEnum):
    INITIAL_DIAGNOSTIC = "initial_diagnostic"


class AssessmentStatus(StrEnum):
    DRAFT = "draft"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
