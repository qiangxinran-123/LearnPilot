from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from backend.app.models import (
    ConfidenceLevel,
    LearningSessionStatus,
    LearningSessionTaskPhase,
    LearningSessionTaskStatus,
    MasteryStatus,
    QuestionDifficulty,
    QuestionType,
    TeachingStrategy,
    TutorMessageRole,
)
from backend.app.schemas.diagnostic import QuestionOptionSchema
from backend.app.schemas.learning_content import LearningContentSegmentRead


class TutorMessageCreate(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    mode: TeachingStrategy = TeachingStrategy.GUIDED_QUESTION

    @field_validator("message")
    @classmethod
    def message_must_contain_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Message must not be blank.")
        return normalized


class TutorGeneratedCitation(BaseModel):
    material_id: int = Field(gt=0)
    source_reference: str = Field(min_length=1, max_length=255)


class TutorStructuredOutput(BaseModel):
    answer: str = Field(min_length=1, max_length=6000)
    mode: TeachingStrategy
    citations: list[TutorGeneratedCitation] = Field(default_factory=list, max_length=4)
    insufficient_evidence: bool


class TutorCitationRead(BaseModel):
    material_id: int = Field(gt=0)
    material_title: str = Field(min_length=1, max_length=255)
    material_type: str = Field(min_length=1, max_length=50)
    source_reference: str = Field(min_length=1, max_length=255)
    content_hash: str = Field(min_length=64, max_length=64)


class TutorMessageRead(BaseModel):
    message_id: int = Field(gt=0)
    exchange_id: str = Field(min_length=36, max_length=36)
    session_id: int = Field(gt=0)
    task_state_id: int | None = Field(default=None, gt=0)
    role: TutorMessageRole
    mode: TeachingStrategy
    content: str
    citations: list[TutorCitationRead]
    grounded: bool
    insufficient_evidence: bool
    created_at: datetime


class TutorExchangeRead(BaseModel):
    session_id: int = Field(gt=0)
    user_message: TutorMessageRead
    tutor_message: TutorMessageRead
    reused: bool = False


class TutorMessageListRead(BaseModel):
    session_id: int = Field(gt=0)
    messages: list[TutorMessageRead]


class TutorCurrentTaskContext(BaseModel):
    task_state_id: int = Field(gt=0)
    phase: LearningSessionTaskPhase
    status: LearningSessionTaskStatus


class TutorMasteryContext(BaseModel):
    mastery_status: MasteryStatus
    confidence_level: ConfidenceLevel
    mastery_score: str | None
    calculation_state: str


class TutorPracticeQuestionContext(BaseModel):
    assessment_question_id: int = Field(gt=0)
    question_id: int = Field(gt=0)
    question_type: QuestionType
    stem: str
    options: list[QuestionOptionSchema]
    difficulty: QuestionDifficulty
    answer_submitted: bool
    selected_options: list[str] | None = None
    correct_answer: list[str] | None = None
    explanation: str | None = None
    is_correct: bool | None = None


class TutorContext(BaseModel):
    session_id: int = Field(gt=0)
    session_status: LearningSessionStatus
    course_id: int = Field(gt=0)
    course_name: str
    knowledge_node_id: int = Field(gt=0)
    knowledge_node_name: str
    knowledge_node_description: str
    learning_goal: str
    current_task: TutorCurrentTaskContext
    mastery_state: TutorMasteryContext
    practice_question: TutorPracticeQuestionContext | None = None
    source_context: list[LearningContentSegmentRead]
    recent_messages: list[TutorMessageRead]


__all__ = [
    "TutorCitationRead",
    "TutorContext",
    "TutorCurrentTaskContext",
    "TutorExchangeRead",
    "TutorGeneratedCitation",
    "TutorMasteryContext",
    "TutorPracticeQuestionContext",
    "TutorMessageCreate",
    "TutorMessageListRead",
    "TutorMessageRead",
    "TutorStructuredOutput",
]
