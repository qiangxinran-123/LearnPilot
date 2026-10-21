from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.models import (
    AssessmentStatus,
    AssessmentType,
    KnowledgeRelationRole,
    QuestionDifficulty,
    QuestionType,
    QuestionValidationStatus,
)


class QuestionOptionSchema(BaseModel):
    key: str = Field(min_length=1, max_length=32, pattern=r"^[A-Z][A-Z0-9_]*$")
    text: str = Field(min_length=1, max_length=2000)

    @field_validator("key")
    @classmethod
    def normalize_key(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("text")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Option text must not be blank.")
        return normalized


class QuestionSourceRefSchema(BaseModel):
    material_id: int | None = Field(default=None, gt=0)
    material_title: str | None = Field(default=None, min_length=1, max_length=255)
    source_reference: str = Field(min_length=1, max_length=255)
    excerpt: str | None = Field(default=None, max_length=1000)

    @field_validator("material_title", "excerpt", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: Any) -> Any:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @field_validator("source_reference")
    @classmethod
    def normalize_reference(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Source reference must not be blank.")
        return normalized


class QuestionContentSchema(BaseModel):
    question_type: QuestionType
    stem: str = Field(min_length=1, max_length=10000)
    options: list[QuestionOptionSchema] = Field(min_length=2, max_length=20)
    correct_answer: list[str] = Field(min_length=1, max_length=20)
    explanation: str = Field(min_length=1, max_length=10000)
    difficulty: QuestionDifficulty
    source_refs: list[QuestionSourceRefSchema] = Field(default_factory=list, max_length=100)

    @field_validator("stem", "explanation")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Required question text must not be blank.")
        return normalized

    @field_validator("correct_answer")
    @classmethod
    def normalize_answers(cls, value: list[str]) -> list[str]:
        normalized = [item.strip().upper() for item in value]
        if any(not item for item in normalized):
            raise ValueError("Correct answer keys must not be blank.")
        if len(normalized) != len(set(normalized)):
            raise ValueError("Correct answer keys must be unique.")
        return normalized

    @model_validator(mode="after")
    def validate_objective_contract(self) -> Self:
        keys = [option.key for option in self.options]
        if len(keys) != len(set(keys)):
            raise ValueError("Option keys must be unique.")
        unknown = set(self.correct_answer) - set(keys)
        if unknown:
            raise ValueError("Correct answer keys must reference declared options.")
        if self.question_type in {QuestionType.SINGLE_CHOICE, QuestionType.TRUE_FALSE}:
            if len(self.correct_answer) != 1:
                raise ValueError("Single-choice and true/false questions require exactly one answer key.")
        elif len(self.correct_answer) < 2:
            raise ValueError("Multiple-choice questions require at least two answer keys.")
        if self.question_type == QuestionType.TRUE_FALSE and keys != ["TRUE", "FALSE"]:
            raise ValueError("True/false options must be ordered as TRUE then FALSE.")
        order = {key: index for index, key in enumerate(keys)}
        self.correct_answer = sorted(self.correct_answer, key=order.__getitem__)
        return self


class QuestionKnowledgeBindingSchema(BaseModel):
    knowledge_node_id: int = Field(gt=0)
    relation_role: KnowledgeRelationRole


class QuestionKnowledgeRefSchema(BaseModel):
    id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=255)
    role: KnowledgeRelationRole

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Knowledge node name must not be blank.")
        return normalized


class QuestionCreateSchema(BaseModel):
    content: QuestionContentSchema
    knowledge_nodes: list[QuestionKnowledgeBindingSchema] = Field(min_length=1, max_length=100)
    validation_status: QuestionValidationStatus = QuestionValidationStatus.PENDING
    generation_metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_knowledge_bindings(self) -> Self:
        node_ids = [item.knowledge_node_id for item in self.knowledge_nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("Knowledge node bindings must be unique.")
        primary_count = sum(item.relation_role == KnowledgeRelationRole.PRIMARY for item in self.knowledge_nodes)
        if primary_count != 1:
            raise ValueError("A question must have exactly one primary knowledge node.")
        return self


class ScoringPolicySchema(BaseModel):
    version: Literal["objective_exact_match_v1"] = "objective_exact_match_v1"
    max_points: Annotated[int, Field(gt=0, le=100)] = 1


class AssessmentQuestionSnapshotSchema(QuestionContentSchema):
    schema_version: Literal["assessment_question_v1"] = "assessment_question_v1"
    source_question_id: int = Field(gt=0)
    source_question_version: int = Field(ge=1)
    knowledge_nodes: list[QuestionKnowledgeRefSchema] = Field(min_length=1, max_length=100)
    knowledge_model_version: str | None = Field(default=None, max_length=120)
    scoring_policy: ScoringPolicySchema = Field(default_factory=ScoringPolicySchema)

    @model_validator(mode="after")
    def validate_historical_knowledge_refs(self) -> Self:
        node_ids = [item.id for item in self.knowledge_nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("Historical knowledge node references must be unique.")
        primary_count = sum(item.role == KnowledgeRelationRole.PRIMARY for item in self.knowledge_nodes)
        if primary_count != 1:
            raise ValueError("A snapshot must contain exactly one primary knowledge node.")
        return self


class ObjectiveAnswerSchema(BaseModel):
    schema_version: Literal["objective_answer_v1"] = "objective_answer_v1"
    selected_options: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("selected_options")
    @classmethod
    def normalize_selected_options(cls, value: list[str]) -> list[str]:
        normalized = [item.strip().upper() for item in value]
        if any(not item for item in normalized):
            raise ValueError("Selected option keys must not be blank.")
        if len(normalized) != len(set(normalized)):
            raise ValueError("Selected option keys must be unique.")
        return sorted(normalized)


class AssessmentStatusSchema(BaseModel):
    status: AssessmentStatus


class CandidateQuestionSchema(BaseModel):
    """Candidate-safe view: deliberately excludes answers, explanation and scoring policy."""

    question_type: QuestionType
    stem: str
    options: list[QuestionOptionSchema]
    difficulty: QuestionDifficulty
    order_index: int = Field(ge=0)


class AssessmentResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    assessment_id: int
    assessment_question_id: int
    answer_payload: dict[str, Any]
    answered_at: datetime
    submitted_at: datetime | None
    is_correct: bool | None
    points_awarded: float | None


class AssessmentSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    course_id: int
    owner_id: int
    assessment_type: AssessmentType
    status: AssessmentStatus
    created_at: datetime
    started_at: datetime | None
    submitted_at: datetime | None
    updated_at: datetime


class DiagnosticNodeResultContract(BaseModel):
    """Future M4-E output contract; M4-A does not calculate or persist it."""

    knowledge_node: QuestionKnowledgeRefSchema
    earned_points: float = Field(ge=0)
    max_points: float = Field(gt=0)


class DiagnosticResultContract(BaseModel):
    """Future deterministic result contract; M4-A provides no scorer."""

    assessment_id: int = Field(gt=0)
    scoring_engine: Literal["deterministic"] = "deterministic"
    node_results: list[DiagnosticNodeResultContract]
