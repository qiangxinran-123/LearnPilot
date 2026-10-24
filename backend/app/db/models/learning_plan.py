from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import JSON, CheckConstraint, Enum, ForeignKey, ForeignKeyConstraint, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, TimestampMixin
from backend.app.models import LearningPlanStatus

if TYPE_CHECKING:
    from backend.app.db.models.learning_task import LearningTask


def _status_values(enum_type: type[LearningPlanStatus]) -> list[str]:
    return [member.value for member in enum_type]


class LearningPlan(TimestampMixin, Base):
    __tablename__ = "learning_plans"
    __table_args__ = (
        ForeignKeyConstraint(
            ["course_id", "target_node_id"],
            ["knowledge_nodes.course_id", "knowledge_nodes.id"],
            ondelete="CASCADE",
            name="fk_learning_plans_target_in_course",
        ),
        UniqueConstraint("user_id", "course_id", "active_slot", name="uq_learning_plans_active_slot"),
        CheckConstraint("priority_score >= 0 AND priority_score <= 1", name="ck_learning_plans_priority_score"),
        CheckConstraint("length(context_fingerprint) = 64", name="ck_learning_plans_context_fingerprint"),
        CheckConstraint(
            "(status = 'available' AND active_slot = 1) OR (status = 'superseded' AND active_slot IS NULL)",
            name="ck_learning_plans_status_active_slot",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    target_node_id: Mapped[int] = mapped_column(nullable=False, index=True)
    reason_codes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    priority_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    priority_breakdown: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    prerequisite_evidence: Mapped[list[dict[str, str | int]]] = mapped_column(JSON, nullable=False)
    blocked_target_node_ids: Mapped[list[int]] = mapped_column(JSON, nullable=False)
    context_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[LearningPlanStatus] = mapped_column(
        Enum(
            LearningPlanStatus,
            values_callable=_status_values,
            native_enum=False,
            create_constraint=True,
            name="learning_plan_status",
        ),
        nullable=False,
    )
    active_slot: Mapped[int | None] = mapped_column(nullable=True)
    plan_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)

    tasks: Mapped[list[LearningTask]] = relationship(
        back_populates="plan",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="LearningTask.order_index",
    )
