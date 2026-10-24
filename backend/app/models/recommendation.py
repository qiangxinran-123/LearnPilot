from enum import StrEnum


class DataAvailability(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class CandidateEligibilityStatus(StrEnum):
    ELIGIBLE = "eligible"
    UNASSESSED = "unassessed"
    LOW_CONFIDENCE = "low_confidence"
    MASTERED = "mastered"
    INVALID = "invalid"


class CandidateExclusionReason(StrEnum):
    MISSING_MASTERY = "missing_mastery"
    STALE_MASTERY = "stale_mastery"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    LOW_CONFIDENCE = "low_confidence"
    ALREADY_MASTERED = "already_mastered"
    COURSE_MISMATCH = "course_mismatch"
    INVALID_STATE = "invalid_state"


class PrerequisiteEvaluationStatus(StrEnum):
    NOT_EVALUATED = "not_evaluated"
    SATISFIED = "satisfied"
    UNSATISFIED = "unsatisfied"
    INVALID = "invalid"


class PrerequisiteEvidenceStatus(StrEnum):
    SATISFIED = "satisfied"
    UNSATISFIED = "unsatisfied"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    INVALID = "invalid"


class RecommendationAvailabilityStatus(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    NEEDS_INITIAL_DIAGNOSTIC = "needs_initial_diagnostic"
    NEEDS_PREREQUISITE_ASSESSMENT = "needs_prerequisite_assessment"
    NO_ELIGIBLE_CANDIDATE = "no_eligible_candidate"
    ALL_MASTERED = "all_mastered"
    INVALID_CONTEXT = "invalid_context"


class RecommendationReasonCode(StrEnum):
    KNOWLEDGE_GAP = "knowledge_gap"
    LOW_MASTERY = "low_mastery"
    PREREQUISITE_GAP = "prerequisite_gap"
    PREREQUISITE_FOR_OTHER_NODES = "prerequisite_for_other_nodes"
    HIGH_COURSE_IMPORTANCE = "high_course_importance"
    REVIEW_NEEDED = "review_needed"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    NEUTRAL_COURSE_IMPORTANCE = "neutral_course_importance"
    NEUTRAL_REVIEW_RISK = "neutral_review_risk"
    NO_ELIGIBLE_CANDIDATE = "no_eligible_candidate"
    ALL_MASTERED = "all_mastered"
    INVALID_PREREQUISITE_GRAPH = "invalid_prerequisite_graph"


__all__ = [
    "CandidateEligibilityStatus",
    "CandidateExclusionReason",
    "DataAvailability",
    "PrerequisiteEvidenceStatus",
    "PrerequisiteEvaluationStatus",
    "RecommendationAvailabilityStatus",
    "RecommendationReasonCode",
]
