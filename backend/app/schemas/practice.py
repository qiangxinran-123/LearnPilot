from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from backend.app.models import QuestionDifficulty, QuestionType
from backend.app.schemas.diagnostic import ObjectiveAnswerSchema, QuestionOptionSchema, QuestionSourceRefSchema


class PracticeAnswerCreate(ObjectiveAnswerSchema):
    pass


class PracticeQuestionRead(BaseModel):
    assessment_question_id: int = Field(gt=0)
    question_id: int = Field(gt=0)
    question_number: int = Field(ge=1)
    question_type: QuestionType
    stem: str
    options: list[QuestionOptionSchema]
    difficulty: QuestionDifficulty


class PracticeAttemptRead(BaseModel):
    attempt_id: int = Field(gt=0)
    assessment_question_id: int = Field(gt=0)
    question_id: int = Field(gt=0)
    question_number: int = Field(ge=1)
    question_type: QuestionType
    stem: str
    options: list[QuestionOptionSchema]
    selected_options: list[str]
    correct_answer: list[str]
    explanation: str
    difficulty: QuestionDifficulty
    is_correct: bool
    points_awarded: Decimal = Field(ge=0)
    source_refs: list[QuestionSourceRefSchema]
    submitted_at: datetime


class PracticeSummaryRead(BaseModel):
    answered_count: int = Field(ge=0)
    correct_count: int = Field(ge=0)
    accuracy: Decimal = Field(ge=0, le=1)


class PracticeRead(BaseModel):
    session_id: int = Field(gt=0)
    knowledge_node_id: int = Field(gt=0)
    assessment_id: int = Field(gt=0)
    status: Literal["in_progress", "completed", "question_bank_empty"]
    current_difficulty: QuestionDifficulty
    current_question: PracticeQuestionRead | None
    answered_count: int = Field(ge=0)
    max_questions: int = Field(ge=1)
    attempts: list[PracticeAttemptRead]
    summary: PracticeSummaryRead | None
    reused: bool = False


__all__ = [
    "PracticeAnswerCreate",
    "PracticeAttemptRead",
    "PracticeQuestionRead",
    "PracticeRead",
    "PracticeSummaryRead",
]
