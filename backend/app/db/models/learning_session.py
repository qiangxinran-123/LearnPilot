from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, CheckConstraint, Enum, ForeignKey, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, TimestampMixin
from backend.app.models import LearningSessionStatus, RecommendationRefreshStatus

if TYPE_CHECKING:
    from backend.app.db.models.course import Course
    from backend.app.db.models.knowledge_node import KnowledgeNode
    from backend.app.db.models.learning_session_task_state import LearningSessionTaskState


def _status_values(enum_type: type[LearningSessionStatus]) -> list[str]:
    return [member.value for member in enum_type]


class LearningSession(TimestampMixin, Base):
    __tablename__ = "learning_sessions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["course_id", "target_knowledge_node_id"],
            ["knowledge_nodes.course_id", "knowledge_nodes.id"],
            ondelete="RESTRICT",
            name="fk_learning_sessions_target_in_course",
        ),
        UniqueConstraint(
            "user_id",
            "course_id",
            "target_knowledge_node_id",
            "active_slot",
            name="uq_learning_sessions_active_target",
        ),
        CheckConstraint(
            "(status IN ('created', 'in_progress') AND active_slot = 1) OR "
            "(status IN ('completed', 'cancelled') AND active_slot IS NULL)",
            name="ck_learning_sessions_status_active_slot",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    target_knowledge_node_id: Mapped[int] = mapped_column(nullable=False, index=True)
    source_learning_plan_id: Mapped[int | None] = mapped_column(
        ForeignKey("learning_plans.id", ondelete="SET NULL"), nullable=True, index=True
    )
    practice_assessment_id: Mapped[int | None] = mapped_column(
        ForeignKey("assessments.id", ondelete="SET NULL"), nullable=True, unique=True
    )
    status: Mapped[LearningSessionStatus] = mapped_column(
        Enum(
            LearningSessionStatus,
            values_callable=_status_values,
            native_enum=False,
            create_constraint=True,
            name="learning_session_status",
        ),
        nullable=False,
    )
    active_slot: Mapped[int | None] = mapped_column(nullable=True)
    session_contract_version: Mapped[str] = mapped_column(String(64), nullable=False)
    completion_summary: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    recommendation_refresh_status: Mapped[RecommendationRefreshStatus] = mapped_column(
        Enum(
            RecommendationRefreshStatus,
            values_callable=lambda enum_type: [member.value for member in enum_type],
            native_enum=False,
            create_constraint=True,
            name="recommendation_refresh_status",
        ),
        default=RecommendationRefreshStatus.NOT_REQUESTED,
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(nullable=True)

    course: Mapped[Course] = relationship()
    target_knowledge_node: Mapped[KnowledgeNode] = relationship(foreign_keys=[target_knowledge_node_id])
    tasks: Mapped[list[LearningSessionTaskState]] = relationship(
        back_populates="learning_session",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="LearningSessionTaskState.order_index",
    )
