from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, TimestampMixin
from backend.app.models import AssessmentStatus, AssessmentType

if TYPE_CHECKING:
    from backend.app.db.models.assessment_question import AssessmentQuestion
    from backend.app.db.models.course import Course
    from backend.app.db.models.response import Response
    from backend.app.db.models.user import User


def _enum_values(enum_type: type) -> list[str]:
    return [member.value for member in enum_type]


class Assessment(TimestampMixin, Base):
    __tablename__ = "assessments"
    __table_args__ = (UniqueConstraint("id", "course_id", name="uq_assessments_id_course_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    assessment_type: Mapped[AssessmentType] = mapped_column(
        Enum(
            AssessmentType,
            values_callable=_enum_values,
            native_enum=False,
            create_constraint=True,
            name="assessment_type",
        ),
        default=AssessmentType.INITIAL_DIAGNOSTIC,
        nullable=False,
    )
    status: Mapped[AssessmentStatus] = mapped_column(
        Enum(
            AssessmentStatus,
            values_callable=_enum_values,
            native_enum=False,
            create_constraint=True,
            name="assessment_status",
        ),
        default=AssessmentStatus.DRAFT,
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    report_policy_version: Mapped[str | None] = mapped_column(String(64), nullable=True)

    course: Mapped[Course] = relationship()
    owner: Mapped[User] = relationship()
    questions: Mapped[list[AssessmentQuestion]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan", order_by="AssessmentQuestion.order_index"
    )
    responses: Mapped[list[Response]] = relationship(back_populates="assessment", cascade="all, delete-orphan")
