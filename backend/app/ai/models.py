from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.app.models import (
    KnowledgeDifficulty,
    KnowledgeImportance,
    QuestionDifficulty,
    QuestionType,
)


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


class DiagnosticQuestionOptionDraft(BaseModel):
    key: str = Field(min_length=1, max_length=32, pattern=r"^[A-Z][A-Z0-9_]*$")
    text: str = Field(min_length=1, max_length=2000)

    @field_validator("key")
    @classmethod
    def normalize_key(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("text")
    @classmethod
    def normalize_option_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Question option text must not be blank.")
        return normalized


class DiagnosticQuestionSourceDraft(BaseModel):
    material_id: int = Field(gt=0)
    source_reference: str = Field(min_length=1, max_length=255)

    @field_validator("source_reference")
    @classmethod
    def normalize_source_reference(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("A source reference must not be blank.")
        return normalized


class DiagnosticQuestionDraft(BaseModel):
    question_type: QuestionType
    stem: str = Field(min_length=1, max_length=10000)
    options: list[DiagnosticQuestionOptionDraft] = Field(min_length=2, max_length=20)
    correct_answer: list[str] = Field(min_length=1, max_length=20)
    explanation: str = Field(min_length=1, max_length=10000)
    difficulty: QuestionDifficulty
    knowledge_node_ids: list[int] = Field(min_length=1, max_length=8)
    source_refs: list[DiagnosticQuestionSourceDraft] = Field(min_length=1, max_length=8)

    @field_validator("stem", "explanation")
    @classmethod
    def normalize_question_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Question text must not be blank.")
        return normalized

    @field_validator("correct_answer")
    @classmethod
    def normalize_answers(cls, values: list[str]) -> list[str]:
        normalized = [value.strip().upper() for value in values]
        if any(not value for value in normalized) or len(normalized) != len(set(normalized)):
            raise ValueError("Correct answer keys must be non-empty and unique.")
        return normalized

    @field_validator("knowledge_node_ids")
    @classmethod
    def unique_node_ids(cls, values: list[int]) -> list[int]:
        if any(value <= 0 for value in values) or len(values) != len(set(values)):
            raise ValueError("Knowledge node IDs must be positive and unique.")
        return values

    @model_validator(mode="after")
    def validate_objective_answer(self) -> "DiagnosticQuestionDraft":
        option_keys = [option.key for option in self.options]
        if len(option_keys) != len(set(option_keys)):
            raise ValueError("Option keys must be unique.")
        if set(self.correct_answer) - set(option_keys):
            raise ValueError("Correct answers must reference declared option keys.")
        if self.question_type in {QuestionType.SINGLE_CHOICE, QuestionType.TRUE_FALSE}:
            if len(self.correct_answer) != 1:
                raise ValueError("Single choice and true/false require exactly one answer.")
        elif len(self.correct_answer) < 2:
            raise ValueError("Multiple choice requires at least two correct answers.")
        if self.question_type == QuestionType.TRUE_FALSE and option_keys != ["TRUE", "FALSE"]:
            raise ValueError("True/false options must be TRUE then FALSE.")
        order = {key: index for index, key in enumerate(option_keys)}
        self.correct_answer = sorted(self.correct_answer, key=order.__getitem__)
        return self


class DiagnosticQuestionGenerationOutput(BaseModel):
    questions: list[DiagnosticQuestionDraft] = Field(min_length=1, max_length=8)
