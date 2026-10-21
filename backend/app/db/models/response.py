from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, ForeignKeyConstraint, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from backend.app.db.models.assessment import Assessment
    from backend.app.db.models.assessment_question import AssessmentQuestion


class Response(TimestampMixin, Base):
    __tablename__ = "responses"
    __table_args__ = (
        ForeignKeyConstraint(
            ["assessment_id", "assessment_question_id"],
            ["assessment_questions.assessment_id", "assessment_questions.id"],
            ondelete="CASCADE",
            name="fk_responses_assessment_question",
        ),
        UniqueConstraint("assessment_question_id", name="uq_responses_assessment_question_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assessment_question_id: Mapped[int] = mapped_column(nullable=False)
    answer_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    answered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    points_awarded: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)

    assessment: Mapped[Assessment] = relationship(back_populates="responses", overlaps="assessment_question,response")
    assessment_question: Mapped[AssessmentQuestion] = relationship(
        back_populates="response", overlaps="assessment,responses"
    )
