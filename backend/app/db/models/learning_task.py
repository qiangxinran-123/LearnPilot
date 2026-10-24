from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, TimestampMixin
from backend.app.models import LearningTaskType

if TYPE_CHECKING:
    from backend.app.db.models.learning_plan import LearningPlan


def _task_type_values(enum_type: type[LearningTaskType]) -> list[str]:
    return [member.value for member in enum_type]


class LearningTask(TimestampMixin, Base):
    __tablename__ = "learning_tasks"
    __table_args__ = (
        UniqueConstraint("plan_id", "order_index", name="uq_learning_tasks_plan_order"),
        CheckConstraint("order_index >= 0 AND order_index <= 2", name="ck_learning_tasks_order_index"),
        CheckConstraint(
            "estimated_minutes IS NULL OR estimated_minutes > 0",
            name="ck_learning_tasks_estimated_minutes",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("learning_plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    knowledge_node_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_type: Mapped[LearningTaskType] = mapped_column(
        Enum(
            LearningTaskType,
            values_callable=_task_type_values,
            native_enum=False,
            create_constraint=True,
            name="learning_task_type",
        ),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    order_index: Mapped[int] = mapped_column(nullable=False)
    estimated_minutes: Mapped[int | None] = mapped_column(nullable=True)

    plan: Mapped[LearningPlan] = relationship(back_populates="tasks")
