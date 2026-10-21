from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from backend.app.models import QuestionDifficulty, QuestionType
from backend.app.schemas.diagnostic import CandidateQuestionSchema


class QuestionBankStatisticsSchema(BaseModel):
    available_questions: int = Field(ge=0)
    eligible_knowledge_nodes: int = Field(ge=0)
    covered_knowledge_nodes: int = Field(ge=0)
    required_questions: int = Field(ge=8, le=20)


class AssemblyMetadataSchema(BaseModel):
    strategy_version: str = "knowledge_coverage_greedy_v1"
    question_count: int = Field(ge=8, le=20)
    eligible_knowledge_nodes: int = Field(ge=1)
    covered_knowledge_nodes: int = Field(ge=1)
    question_type_distribution: dict[QuestionType, int]
    difficulty_distribution: dict[QuestionDifficulty, int]


class CandidateAssessmentQuestionSchema(CandidateQuestionSchema):
    assessment_question_id: int = Field(gt=0)


class ObjectiveScoreResultSchema(BaseModel):
    is_correct: bool
    points_awarded: Decimal = Field(ge=0)
    max_points: Decimal = Field(gt=0)
    scoring_policy_version: str


class AssessmentScoreSummarySchema(BaseModel):
    assessment_id: int = Field(gt=0)
    total_questions: int = Field(ge=0)
    answered_questions: int = Field(ge=0)
    correct_questions: int = Field(ge=0)
    total_points: Decimal = Field(ge=0)
    earned_points: Decimal = Field(ge=0)
    accuracy: Decimal = Field(ge=0, le=1)


class AssessmentReadinessSchema(BaseModel):
    course_id: int = Field(gt=0)
    status: Literal["ready", "knowledge_not_ready", "question_bank_insufficient"]
    can_start: bool
    estimated_question_count: int | None = Field(default=None, ge=8, le=20)
    estimated_minutes: int | None = Field(default=None, ge=1)
    eligible_knowledge_nodes: int = Field(ge=0)
    covered_knowledge_nodes: int = Field(ge=0)
    available_questions: int = Field(ge=0)
    required_questions: int = Field(default=8, ge=8, le=20)
    reason_code: str | None = None
    message: str
