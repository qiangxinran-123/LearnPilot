from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base
from backend.app.models import TeachingStrategy, TutorMessageRole


def _enum_values(enum_type: type[TeachingStrategy] | type[TutorMessageRole]) -> list[str]:
    return [member.value for member in enum_type]


class TutorMessage(Base):
    __tablename__ = "tutor_messages"
    __table_args__ = (
        UniqueConstraint("session_id", "exchange_id", "role", name="uq_tutor_messages_exchange_role"),
        UniqueConstraint("session_id", "idempotency_key", name="uq_tutor_messages_idempotency"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("learning_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_state_id: Mapped[int | None] = mapped_column(
        ForeignKey("learning_session_task_states.id", ondelete="SET NULL"), nullable=True, index=True
    )
    exchange_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    role: Mapped[TutorMessageRole] = mapped_column(
        Enum(
            TutorMessageRole,
            values_callable=_enum_values,
            native_enum=False,
            create_constraint=True,
            name="tutor_message_role",
        ),
        nullable=False,
    )
    teaching_strategy: Mapped[TeachingStrategy] = mapped_column(
        Enum(
            TeachingStrategy,
            values_callable=_enum_values,
            native_enum=False,
            create_constraint=True,
            name="teaching_strategy",
        ),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list, nullable=False)
    grounded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    insufficient_evidence: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    model: Mapped[str | None] = mapped_column(String(160), nullable=True)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


__all__ = ["TutorMessage"]
