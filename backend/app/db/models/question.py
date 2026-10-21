from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, CheckConstraint, Enum, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, TimestampMixin
from backend.app.models import QuestionDifficulty, QuestionType, QuestionValidationStatus

if TYPE_CHECKING:
    from backend.app.db.models.assessment_question import AssessmentQuestion
    from backend.app.db.models.course import Course
    from backend.app.db.models.question_knowledge_node import QuestionKnowledgeNode


def _enum_values(enum_type: type) -> list[str]:
    return [member.value for member in enum_type]


class Question(TimestampMixin, Base):
    __tablename__ = "questions"
    __table_args__ = (
        UniqueConstraint("course_id", "id", name="uq_questions_course_id_id"),
        CheckConstraint("content_version >= 1", name="ck_questions_content_version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    question_type: Mapped[QuestionType] = mapped_column(
        Enum(
            QuestionType,
            values_callable=_enum_values,
            native_enum=False,
            create_constraint=True,
            name="question_type",
        ),
        nullable=False,
    )
    stem: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[list[dict[str, str]]] = mapped_column(JSON, nullable=False)
    correct_answer: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty: Mapped[QuestionDifficulty] = mapped_column(
        Enum(
            QuestionDifficulty,
            values_callable=_enum_values,
            native_enum=False,
            create_constraint=True,
            name="question_difficulty",
        ),
        nullable=False,
    )
    validation_status: Mapped[QuestionValidationStatus] = mapped_column(
        Enum(
            QuestionValidationStatus,
            values_callable=_enum_values,
            native_enum=False,
            create_constraint=True,
            name="question_validation_status",
        ),
        default=QuestionValidationStatus.PENDING,
        nullable=False,
    )
    source_refs: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    generation_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    content_version: Mapped[int] = mapped_column(default=1, nullable=False)

    course: Mapped[Course] = relationship()
    knowledge_links: Mapped[list[QuestionKnowledgeNode]] = relationship(
        back_populates="question", cascade="all, delete-orphan"
    )
    assessment_questions: Mapped[list[AssessmentQuestion]] = relationship(back_populates="source_question")
