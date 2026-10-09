from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base
from backend.app.models import KnowledgeRelationshipStatus


def _status_values(enum_type: type[KnowledgeRelationshipStatus]) -> list[str]:
    return [member.value for member in enum_type]


class KnowledgeRelationshipRun(Base):
    __tablename__ = "knowledge_relationship_runs"
    __table_args__ = (
        CheckConstraint("node_count >= 0", name="ck_knowledge_relationship_runs_node_count"),
        CheckConstraint("contains_edge_count >= 0", name="ck_knowledge_relationship_runs_contains_count"),
        CheckConstraint(
            "prerequisite_edge_count >= 0",
            name="ck_knowledge_relationship_runs_prerequisite_count",
        ),
        CheckConstraint("rejected_edge_count >= 0", name="ck_knowledge_relationship_runs_rejected_count"),
        UniqueConstraint("id", "course_id", name="uq_knowledge_relationship_runs_id_course"),
        Index(
            "ix_knowledge_relationship_runs_idempotency",
            "course_id",
            "knowledge_snapshot_hash",
            "prompt_version",
            "model",
        ),
        Index("ix_knowledge_relationship_runs_course_current", "course_id", "is_current"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    knowledge_snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[KnowledgeRelationshipStatus] = mapped_column(
        Enum(
            KnowledgeRelationshipStatus,
            values_callable=_status_values,
            native_enum=False,
            create_constraint=True,
            name="knowledge_relationship_status",
        ),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model: Mapped[str] = mapped_column(String(160), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(80), nullable=False)
    node_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    contains_edge_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    prerequisite_edge_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rejected_edge_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
