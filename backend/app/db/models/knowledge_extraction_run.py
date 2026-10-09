from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base
from backend.app.models import KnowledgeExtractionStatus

if TYPE_CHECKING:
    from backend.app.db.models.knowledge_candidate import KnowledgeCandidate


def _status_values(enum_type: type[KnowledgeExtractionStatus]) -> list[str]:
    return [member.value for member in enum_type]


class KnowledgeExtractionRun(Base):
    __tablename__ = "knowledge_extraction_runs"
    __table_args__ = (
        CheckConstraint("candidate_count >= 0", name="ck_knowledge_extraction_runs_candidate_count"),
        UniqueConstraint(
            "id",
            "course_id",
            "material_id",
            name="uq_knowledge_extraction_runs_id_course_material",
        ),
        Index(
            "ix_knowledge_extraction_runs_idempotency",
            "material_id",
            "material_content_hash",
            "prompt_version",
            "model",
        ),
        Index("ix_knowledge_extraction_runs_material_current", "material_id", "is_current"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id", ondelete="CASCADE"), nullable=False, index=True)
    material_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[KnowledgeExtractionStatus] = mapped_column(
        Enum(
            KnowledgeExtractionStatus,
            values_callable=_status_values,
            native_enum=False,
            create_constraint=True,
            name="knowledge_extraction_status",
        ),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model: Mapped[str] = mapped_column(String(160), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(80), nullable=False)
    candidate_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
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

    candidates: Mapped[list[KnowledgeCandidate]] = relationship(
        back_populates="extraction_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="KnowledgeCandidate.id",
    )
