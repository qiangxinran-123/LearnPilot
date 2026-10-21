from __future__ import annotations

from pydantic import BaseModel, Field

from backend.app.models import QuestionDifficulty, QuestionType


class QuestionGenerationRequestSchema(BaseModel):
    course_id: int = Field(gt=0)
    knowledge_node_id: int = Field(gt=0)
    question_type: QuestionType
    difficulty: QuestionDifficulty
    count: int = Field(gt=0, le=8)
