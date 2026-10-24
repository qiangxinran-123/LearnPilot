from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from backend.app.models import QuestionDifficulty, QuestionType, QuestionValidationStatus
from backend.app.schemas.diagnostic import QuestionOptionSchema, QuestionSourceRefSchema


class QuestionGenerationRequestSchema(BaseModel):
    course_id: int = Field(gt=0)
    knowledge_node_id: int = Field(gt=0)
    question_type: QuestionType
    difficulty: QuestionDifficulty
    count: int = Field(gt=0, le=8)


class DiagnosticQuestionGenerateRequestSchema(BaseModel):
    knowledge_node_id: int = Field(gt=0)
    count: Literal[1] = 1


class QuestionBankNodeSchema(BaseModel):
    knowledge_node_id: int = Field(gt=0)
    knowledge_node_name: str = Field(min_length=1, max_length=255)
    has_validated_question: bool
    has_pending_question: bool


class QuestionBankReadinessSchema(BaseModel):
    course_id: int = Field(gt=0)
    validated_count: int = Field(ge=0)
    pending_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    covered_core_nodes: int = Field(ge=0)
    total_core_nodes: int = Field(ge=0)
    minimum_required: int = Field(ge=1)
    required_questions: int = Field(ge=1)
    can_start: bool
    reason_code: str | None = None
    required_nodes: list[QuestionBankNodeSchema]


class QuestionBankItemSchema(BaseModel):
    question_id: int = Field(gt=0)
    course_id: int = Field(gt=0)
    knowledge_node_id: int | None = Field(default=None, gt=0)
    knowledge_node_name: str | None = Field(default=None, min_length=1, max_length=255)
    question_type: QuestionType
    difficulty: QuestionDifficulty
    stem: str
    options: list[QuestionOptionSchema]
    correct_answer: list[str]
    explanation: str
    source_refs: list[QuestionSourceRefSchema]
    validation_status: QuestionValidationStatus
    created_at: datetime


class QuestionBankListSchema(BaseModel):
    count: int = Field(ge=0)
    questions: list[QuestionBankItemSchema]


class DiagnosticQuestionGenerationResponseSchema(BaseModel):
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    requested_count: int = Field(ge=1)
    accepted_count: int = Field(ge=0)
    questions: list[QuestionBankItemSchema]


class CourseQuestionPreparationFailureSchema(BaseModel):
    knowledge_node_id: int = Field(gt=0)
    knowledge_node_name: str = Field(min_length=1, max_length=255)
    code: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1)


class CourseQuestionPreparationResponseSchema(BaseModel):
    course_id: int = Field(gt=0)
    planned_count: int = Field(ge=0)
    generated_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    pending_review_count: int = Field(ge=0)
    questions: list[QuestionBankItemSchema]
    failures: list[CourseQuestionPreparationFailureSchema]


class QuestionReviewResponseSchema(BaseModel):
    question: QuestionBankItemSchema
