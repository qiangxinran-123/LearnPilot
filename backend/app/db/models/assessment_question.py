from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base

if TYPE_CHECKING:
    from backend.app.db.models.assessment import Assessment
    from backend.app.db.models.question import Question
    from backend.app.db.models.response import Response


class AssessmentQuestion(Base):
    __tablename__ = "assessment_questions"
    __table_args__ = (
        UniqueConstraint("assessment_id", "id", name="uq_assessment_questions_assessment_id_id"),
        UniqueConstraint("assessment_id", "order_index", name="uq_assessment_questions_assessment_order"),
        UniqueConstraint("assessment_id", "question_id", name="uq_assessment_questions_assessment_question"),
        CheckConstraint("order_index >= 0", name="ck_assessment_questions_order_index"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_id: Mapped[int | None] = mapped_column(
        ForeignKey("questions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    order_index: Mapped[int] = mapped_column(nullable=False)
    question_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    assessment: Mapped[Assessment] = relationship(back_populates="questions")
    source_question: Mapped[Question | None] = relationship(back_populates="assessment_questions")
    response: Mapped[Response | None] = relationship(
        back_populates="assessment_question", uselist=False, overlaps="responses"
    )
