from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.app.models import KnowledgeDifficulty, KnowledgeImportance


class SummaryOutput(BaseModel):
    overview: str = Field(min_length=1, max_length=5000)
    key_concepts: list[str] = Field(min_length=1, max_length=12)
    important_points: list[str] = Field(min_length=1, max_length=12)
    common_mistakes: list[str] = Field(default_factory=list, max_length=8)
    review_suggestions: list[str] = Field(min_length=1, max_length=8)


class StudyCardDraft(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    answer: str = Field(min_length=1, max_length=2000)
    knowledge_hint: str | None = Field(default=None, max_length=500)
    source_reference: str | None = Field(default=None, max_length=255)


class CardsOutput(BaseModel):
    cards: list[StudyCardDraft] = Field(min_length=5, max_length=10)


class QAOutput(BaseModel):
    answer: str = Field(min_length=1, max_length=5000)
    sufficient_evidence: bool
    references: list[str] = Field(max_length=4)

    @model_validator(mode="after")
    def require_grounded_references(self) -> "QAOutput":
        if self.sufficient_evidence and not self.references:
            raise ValueError("Grounded answers require at least one source reference.")
        return self


class KnowledgeCandidateDraft(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=1000)
    importance: KnowledgeImportance
    difficulty: KnowledgeDifficulty
    source_references: list[str] = Field(min_length=1, max_length=6)

    @field_validator("name", "description")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Knowledge candidate text must not be blank.")
        return normalized

    @field_validator("source_references")
    @classmethod
    def normalize_references(cls, values: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(value.strip() for value in values if value.strip()))
        if not normalized:
            raise ValueError("Knowledge candidates require source references.")
        return normalized


class KnowledgeExtractionOutput(BaseModel):
    candidates: list[KnowledgeCandidateDraft] = Field(default_factory=list, max_length=20)


class KnowledgeSemanticMergeDecision(BaseModel):
    candidate_ids: list[int] = Field(min_length=2, max_length=20)
    same_concept: bool
    canonical_name: str | None = Field(default=None, max_length=255)
    canonical_description: str | None = Field(default=None, max_length=1000)
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("candidate_ids")
    @classmethod
    def unique_candidate_ids(cls, values: list[int]) -> list[int]:
        if any(value <= 0 for value in values):
            raise ValueError("Candidate IDs must be positive.")
        if len(values) != len(set(values)):
            raise ValueError("A merge decision cannot repeat a candidate ID.")
        return values

    @model_validator(mode="after")
    def require_canonical_fields_for_merge(self) -> "KnowledgeSemanticMergeDecision":
        if self.same_concept:
            if not self.canonical_name or not self.canonical_name.strip():
                raise ValueError("Same-concept decisions require a canonical name.")
            if not self.canonical_description or not self.canonical_description.strip():
                raise ValueError("Same-concept decisions require a canonical description.")
            self.canonical_name = " ".join(self.canonical_name.split())
            self.canonical_description = " ".join(self.canonical_description.split())
        return self


class KnowledgeCanonicalizationOutput(BaseModel):
    groups: list[KnowledgeSemanticMergeDecision] = Field(default_factory=list, max_length=10)


class KnowledgeRelationshipEvidenceDraft(BaseModel):
    material_id: int | None = Field(default=None, gt=0)
    source_reference: str | None = Field(default=None, min_length=1, max_length=255)

    @model_validator(mode="after")
    def require_complete_material_reference(self) -> "KnowledgeRelationshipEvidenceDraft":
        if (self.material_id is None) != (self.source_reference is None):
            raise ValueError("Relationship evidence requires both material_id and source_reference.")
        if self.source_reference is not None:
            self.source_reference = " ".join(self.source_reference.split())
        return self


class KnowledgeRelationshipEdgeDraft(BaseModel):
    source_node_id: int = Field(gt=0)
    target_node_id: int = Field(gt=0)
    reason: str = Field(min_length=1, max_length=1000)
    evidence: list[KnowledgeRelationshipEvidenceDraft] = Field(default_factory=list, max_length=3)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("A relationship reason must not be blank.")
        return normalized


class KnowledgeRelationshipOutput(BaseModel):
    contains_edges: list[KnowledgeRelationshipEdgeDraft] = Field(default_factory=list, max_length=24)
    prerequisite_edges: list[KnowledgeRelationshipEdgeDraft] = Field(default_factory=list, max_length=24)
