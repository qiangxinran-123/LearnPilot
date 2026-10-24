from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from backend.app.models import AssessmentStatus, QuestionDifficulty, QuestionType
from backend.app.schemas.assessment_scoring import AssessmentReadinessSchema
from backend.app.schemas.diagnostic import ObjectiveAnswerSchema, QuestionOptionSchema


class DiagnosticAssessmentCreateSchema(BaseModel):
    course_id: int = Field(gt=0)


class DiagnosticResponseSaveSchema(ObjectiveAnswerSchema):
    pass


class SavedResponseSchema(BaseModel):
    assessment_question_id: int = Field(gt=0)
    selected_options: list[str]
    answered_at: datetime


class DiagnosticAssessmentDiscardSchema(BaseModel):
    assessment_id: int = Field(gt=0)
    discarded: Literal[True] = True


class DiagnosticCandidateQuestionSchema(BaseModel):
    assessment_question_id: int = Field(gt=0)
    order_index: int = Field(ge=0)
    question_type: QuestionType
    stem: str
    options: list[QuestionOptionSchema]
    difficulty: QuestionDifficulty
    saved_answer: list[str] | None = None


class DiagnosticAssessmentDetailSchema(BaseModel):
    id: int = Field(gt=0)
    course_id: int = Field(gt=0)
    course_name: str
    status: AssessmentStatus
    questions: list[DiagnosticCandidateQuestionSchema]
    question_count: int = Field(ge=0)
    answered_count: int = Field(ge=0)
    created_at: datetime
    started_at: datetime | None
    submitted_at: datetime | None


class DiagnosticAssessmentSummarySchema(BaseModel):
    id: int = Field(gt=0)
    course_id: int = Field(gt=0)
    course_name: str
    status: AssessmentStatus
    question_count: int = Field(ge=0)
    answered_count: int = Field(ge=0)
    correct_questions: int | None = Field(default=None, ge=0)
    accuracy: Decimal | None = Field(default=None, ge=0, le=1)
    created_at: datetime
    submitted_at: datetime | None


class DiagnosticAssessmentListSchema(BaseModel):
    count: int = Field(ge=0)
    assessments: list[DiagnosticAssessmentSummarySchema]


class DiagnosticResultSchema(BaseModel):
    assessment_id: int = Field(gt=0)
    course_id: int = Field(gt=0)
    course_name: str
    submitted_at: datetime
    total_questions: int = Field(ge=0)
    answered_questions: int = Field(ge=0)
    correct_questions: int = Field(ge=0)
    total_points: Decimal = Field(ge=0)
    earned_points: Decimal = Field(ge=0)
    accuracy: Decimal = Field(ge=0, le=1)
    report_policy_version: str = Field(min_length=1, max_length=64)
    covered_knowledge_nodes: int = Field(ge=0)
    needs_attention_nodes: int = Field(ge=0)
    knowledge_performance: list["DiagnosticNodePerformanceSchema"]
    question_reviews: list["DiagnosticQuestionReviewSchema"]


class DiagnosticSourceReferenceSchema(BaseModel):
    material_id: int | None = Field(default=None, gt=0)
    material_title: str | None = None
    source_reference: str
    excerpt: str | None = None
    is_accessible: bool


class DiagnosticHistoricalNodeSchema(BaseModel):
    historical_node_id: int = Field(gt=0)
    historical_node_name: str
    map_available: bool


class DiagnosticNodePerformanceSchema(DiagnosticHistoricalNodeSchema):
    question_count: int = Field(ge=0)
    answered_count: int = Field(ge=0)
    correct_count: int = Field(ge=0)
    incorrect_count: int = Field(ge=0)
    unanswered_count: int = Field(ge=0)
    accuracy: Decimal | None = Field(default=None, ge=0, le=1)
    evidence_status: Literal["not_assessed", "limited_evidence", "basic_evidence"]
    preliminary_status: Literal[
        "not_assessed", "limited_evidence", "needs_attention", "partially_correct", "good_performance"
    ]


class DiagnosticQuestionReviewSchema(BaseModel):
    assessment_question_id: int = Field(gt=0)
    order_index: int = Field(ge=0)
    question_type: QuestionType
    stem: str
    options: list[QuestionOptionSchema]
    selected_options: list[str]
    correct_answer: list[str]
    explanation: str
    is_correct: bool
    points_awarded: Decimal = Field(ge=0)
    primary_node: DiagnosticHistoricalNodeSchema
    secondary_nodes: list[DiagnosticHistoricalNodeSchema]
    source_refs: list[DiagnosticSourceReferenceSchema]


__all__ = [
    "AssessmentReadinessSchema",
    "DiagnosticAssessmentCreateSchema",
    "DiagnosticAssessmentDiscardSchema",
    "DiagnosticAssessmentDetailSchema",
    "DiagnosticAssessmentListSchema",
    "DiagnosticAssessmentSummarySchema",
    "DiagnosticCandidateQuestionSchema",
    "DiagnosticHistoricalNodeSchema",
    "DiagnosticNodePerformanceSchema",
    "DiagnosticQuestionReviewSchema",
    "DiagnosticResponseSaveSchema",
    "DiagnosticResultSchema",
    "DiagnosticSourceReferenceSchema",
    "SavedResponseSchema",
]
