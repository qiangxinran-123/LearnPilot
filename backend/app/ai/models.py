from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


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
