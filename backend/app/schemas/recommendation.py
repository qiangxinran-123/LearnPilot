from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from backend.app.models import (
    CandidateEligibilityStatus,
    CandidateExclusionReason,
    ConfidenceLevel,
    ConfidenceReasonCode,
    DataAvailability,
    EvidenceSourceType,
    KnowledgeDifficulty,
    KnowledgeImportance,
    LearningPlanLevel,
    MasteryStatus,
    PrerequisiteEvaluationStatus,
    PrerequisiteEvidenceStatus,
    RecommendationAvailabilityStatus,
    RecommendationReasonCode,
)
from backend.app.schemas.mastery_api import KnowledgeStateAvailability


class RecommendationKnowledgeNode(BaseModel):
    knowledge_node_id: int = Field(gt=0)
    course_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=255)
    importance: KnowledgeImportance
    difficulty: KnowledgeDifficulty


class RecommendationPrerequisiteEdge(BaseModel):
    source_node_id: int = Field(gt=0)
    target_node_id: int = Field(gt=0)


class RecommendationMasteryState(BaseModel):
    knowledge_node_id: int = Field(gt=0)
    mastery_score: Decimal | None = Field(default=None, ge=0, le=100)
    mastery_status: MasteryStatus
    confidence_level: ConfidenceLevel
    confidence_reason_codes: list[ConfidenceReasonCode]
    evidence_count: int = Field(ge=0)
    independent_evidence_count: int = Field(ge=0)
    assessment_count: int = Field(ge=0)
    calculation_state: KnowledgeStateAvailability
    calculated_at: datetime | None = None

    @model_validator(mode="after")
    def validate_missing_score_semantics(self) -> RecommendationMasteryState:
        if self.calculation_state != KnowledgeStateAvailability.CALCULATED and self.mastery_score is not None:
            raise ValueError("Unavailable or stale mastery cannot expose a score.")
        if self.mastery_status == MasteryStatus.NOT_ASSESSED and self.mastery_score is not None:
            raise ValueError("Unassessed mastery must not expose a score.")
        return self


class EvidenceMetadata(BaseModel):
    knowledge_node_id: int = Field(gt=0)
    evidence_count: int = Field(ge=0)
    assessment_count: int = Field(ge=0)
    source_types: list[EvidenceSourceType]
    latest_evidence_at: datetime | None = None


class ReviewRiskState(BaseModel):
    knowledge_node_id: int = Field(gt=0)
    review_risk: Decimal = Field(ge=0, le=1)


class CandidateNode(BaseModel):
    knowledge_node_id: int = Field(gt=0)
    course_id: int = Field(gt=0)
    mastery_state: MasteryStatus
    mastery_score: Decimal | None = Field(default=None, ge=0, le=100)
    confidence_state: ConfidenceLevel
    prerequisite_ids: list[int] = Field(default_factory=list)
    eligibility_status: CandidateEligibilityStatus
    exclusion_reason: CandidateExclusionReason | None = None

    @model_validator(mode="after")
    def validate_eligibility_reason(self) -> CandidateNode:
        if self.eligibility_status == CandidateEligibilityStatus.ELIGIBLE and self.exclusion_reason is not None:
            raise ValueError("Eligible candidates cannot have an exclusion reason.")
        if self.eligibility_status != CandidateEligibilityStatus.ELIGIBLE and self.exclusion_reason is None:
            raise ValueError("Ineligible candidates require an exclusion reason.")
        return self


class RecommendationContext(BaseModel):
    user_id: int = Field(gt=0)
    course_id: int = Field(gt=0)
    knowledge_nodes: list[RecommendationKnowledgeNode]
    prerequisite_edges: list[RecommendationPrerequisiteEdge]
    mastery_states: list[RecommendationMasteryState]
    evidence_metadata: list[EvidenceMetadata]
    candidates: list[CandidateNode]
    knowledge_importance_availability: DataAvailability
    course_importance_availability: DataAvailability = DataAvailability.UNAVAILABLE
    course_importance: Decimal | None = Field(default=None, ge=0, le=1)
    review_risk_availability: DataAvailability = DataAvailability.UNAVAILABLE
    review_risk_states: list[ReviewRiskState] = Field(default_factory=list)
    latest_valid_assessment_at: datetime | None = None
    needs_initial_diagnostic: bool

    @model_validator(mode="after")
    def validate_node_alignment(self) -> RecommendationContext:
        node_ids = {item.knowledge_node_id for item in self.knowledge_nodes}
        if len(node_ids) != len(self.knowledge_nodes):
            raise ValueError("Knowledge nodes must be unique.")
        for collection in (self.mastery_states, self.evidence_metadata, self.candidates):
            if {item.knowledge_node_id for item in collection} != node_ids:
                raise ValueError("Recommendation context node collections must align.")
        if any(item.course_id != self.course_id for item in self.knowledge_nodes):
            raise ValueError("Knowledge nodes must belong to the context course.")
        if any(item.course_id != self.course_id for item in self.candidates):
            raise ValueError("Candidates must belong to the context course.")
        if self.course_importance_availability == DataAvailability.AVAILABLE:
            if self.course_importance is None:
                raise ValueError("Available course importance requires a value.")
        elif self.course_importance is not None:
            raise ValueError("Unavailable course importance cannot expose a value.")
        review_ids = [item.knowledge_node_id for item in self.review_risk_states]
        if len(review_ids) != len(set(review_ids)) or not set(review_ids).issubset(node_ids):
            raise ValueError("Review risk states must be unique and belong to the context.")
        if self.review_risk_availability == DataAvailability.UNAVAILABLE and review_ids:
            raise ValueError("Unavailable review risk cannot expose values.")
        return self


class PriorityBreakdown(BaseModel):
    knowledge_gap: Decimal | None = Field(default=None, ge=0, le=1)
    dependency_importance: Decimal | None = Field(default=None, ge=0, le=1)
    course_importance: Decimal | None = Field(default=None, ge=0, le=1)
    review_risk: Decimal | None = Field(default=None, ge=0, le=1)
    total_priority: Decimal | None = Field(default=None, ge=0, le=1)


class PrerequisiteEvidence(BaseModel):
    source_node_id: int = Field(gt=0)
    target_node_id: int = Field(gt=0)
    status: PrerequisiteEvidenceStatus


class RecommendationResult(BaseModel):
    user_id: int = Field(gt=0)
    course_id: int = Field(gt=0)
    recommended_node_id: int | None = Field(default=None, gt=0)
    priority_breakdown: PriorityBreakdown
    reason_codes: list[RecommendationReasonCode]
    prerequisite_status: PrerequisiteEvaluationStatus
    availability_status: RecommendationAvailabilityStatus
    plan_level: LearningPlanLevel | None = None
    prerequisite_evidence: list[PrerequisiteEvidence] = Field(default_factory=list)
    blocked_target_node_ids: list[int] = Field(default_factory=list)
    required_assessment_node_ids: list[int] = Field(default_factory=list)
    excluded_invalid_node_ids: list[int] = Field(default_factory=list)
    limited_by_confidence: bool = False

    @model_validator(mode="after")
    def validate_result_availability(self) -> RecommendationResult:
        values = self.priority_breakdown.model_dump().values()
        if self.availability_status == RecommendationAvailabilityStatus.AVAILABLE:
            if self.recommended_node_id is None or self.plan_level is None:
                raise ValueError("Available recommendations require a node and plan level.")
            if self.priority_breakdown.total_priority is None:
                raise ValueError("Available recommendations require a deterministic priority value.")
            if self.plan_level == LearningPlanLevel.PERSONALIZED and any(value is None for value in values):
                raise ValueError("Personalized recommendations require a complete priority breakdown.")
        elif self.recommended_node_id is not None or self.plan_level is not None:
            raise ValueError("Unavailable recommendations cannot expose a node or plan level.")
        return self


__all__ = [
    "CandidateNode",
    "EvidenceMetadata",
    "PriorityBreakdown",
    "PrerequisiteEvidence",
    "RecommendationContext",
    "RecommendationKnowledgeNode",
    "RecommendationMasteryState",
    "RecommendationPrerequisiteEdge",
    "RecommendationResult",
    "ReviewRiskState",
]
