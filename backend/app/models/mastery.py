from enum import StrEnum


class MasteryStatus(StrEnum):
    NOT_ASSESSED = "not_assessed"
    GOOD_PERFORMANCE = "good_performance"
    NEEDS_REINFORCEMENT = "needs_reinforcement"
    POSSIBLY_WEAK = "possibly_weak"
    NEEDS_ATTENTION = "needs_attention"


class ConfidenceLevel(StrEnum):
    INSUFFICIENT = "insufficient"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ConfidenceReasonCode(StrEnum):
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    SINGLE_ASSESSMENT = "single_assessment"
    LIMITED_DIFFICULTY_COVERAGE = "limited_difficulty_coverage"
    PERFORMANCE_VARIATION = "performance_variation"
    SUFFICIENT_EVIDENCE = "sufficient_evidence"
