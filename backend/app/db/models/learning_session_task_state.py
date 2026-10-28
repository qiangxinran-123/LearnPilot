from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, CheckConstraint, Enum, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, TimestampMixin
from backend.app.models import LearningSessionTaskPhase, LearningSessionTaskStatus

if TYPE_CHECKING:
    from backend.app.db.models.learning_session import LearningSession


def _enum_values(enum_type: type[LearningSessionTaskPhase] | type[LearningSessionTaskStatus]) -> list[str]:
    return [member.value for member in enum_type]


class LearningSessionTaskState(TimestampMixin, Base):
    __tablename__ = "learning_session_task_states"
    __table_args__ = (
        UniqueConstraint("session_id", "phase", name="uq_learning_session_tasks_phase"),
        UniqueConstraint("session_id", "order_index", name="uq_learning_session_tasks_order"),
        CheckConstraint("order_index >= 0 AND order_index <= 2", name="ck_learning_session_tasks_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("learning_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_learning_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("learning_tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    phase: Mapped[LearningSessionTaskPhase] = mapped_column(
        Enum(
            LearningSessionTaskPhase,
            values_callable=_enum_values,
            native_enum=False,
            create_constraint=True,
            name="learning_session_task_phase",
        ),
        nullable=False,
    )
    order_index: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[LearningSessionTaskStatus] = mapped_column(
        Enum(
            LearningSessionTaskStatus,
            values_callable=_enum_values,
            native_enum=False,
            create_constraint=True,
            name="learning_session_task_status",
        ),
        nullable=False,
    )
    progress: Mapped[dict[str, str | int | bool]] = mapped_column(JSON, default=dict, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    learning_session: Mapped[LearningSession] = relationship(back_populates="tasks")
