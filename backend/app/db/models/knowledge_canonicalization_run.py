from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base
from backend.app.models import KnowledgeCanonicalizationStatus

if TYPE_CHECKING:
    from backend.app.db.models.knowledge_candidate_resolution import KnowledgeCandidateResolution


def _status_values(enum_type: type[KnowledgeCanonicalizationStatus]) -> list[str]:
    return [member.value for member in enum_type]


class KnowledgeCanonicalizationRun(Base):
    __tablename__ = "knowledge_canonicalization_runs"
    __table_args__ = (
        CheckConstraint("candidate_count >= 0", name="ck_knowledge_canonicalization_candidate_count"),
        CheckConstraint("canonical_node_count >= 0", name="ck_knowledge_canonicalization_node_count"),
        CheckConstraint("merged_candidate_count >= 0", name="ck_knowledge_canonicalization_merged_count"),
        CheckConstraint("unresolved_count >= 0", name="ck_knowledge_canonicalization_unresolved_count"),
        CheckConstraint(
            "canonical_node_count <= candidate_count",
            name="ck_knowledge_canonicalization_nodes_within_candidates",
        ),
        CheckConstraint(
            "merged_candidate_count <= candidate_count",
            name="ck_knowledge_canonicalization_merged_within_candidates",
        ),
        CheckConstraint(
            "unresolved_count <= candidate_count",
            name="ck_knowledge_canonicalization_unresolved_within_candidates",
        ),
        UniqueConstraint("id", "course_id", name="uq_knowledge_canonicalization_runs_id_course"),
        Index(
            "ix_knowledge_canonicalization_idempotency",
            "course_id",
            "candidate_snapshot_hash",
            "prompt_version",
            "model",
            "configuration_version",
        ),
        Index("ix_knowledge_canonicalization_course_current", "course_id", "is_current"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    candidate_snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[KnowledgeCanonicalizationStatus] = mapped_column(
        Enum(
            KnowledgeCanonicalizationStatus,
            values_callable=_status_values,
            native_enum=False,
            create_constraint=True,
            name="knowledge_canonicalization_status",
        ),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model: Mapped[str] = mapped_column(String(160), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(80), nullable=False)
    configuration_version: Mapped[str] = mapped_column(String(80), nullable=False)
    candidate_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    canonical_node_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    merged_candidate_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unresolved_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
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

    resolutions: Mapped[list[KnowledgeCandidateResolution]] = relationship(
        back_populates="canonicalization_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="KnowledgeCandidateResolution.id",
    )
