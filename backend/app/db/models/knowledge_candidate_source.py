from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base

if TYPE_CHECKING:
    from backend.app.db.models.knowledge_candidate import KnowledgeCandidate


class KnowledgeCandidateSource(Base):
    __tablename__ = "knowledge_candidate_sources"
    __table_args__ = (
        ForeignKeyConstraint(
            ["candidate_id", "material_id"],
            ["knowledge_candidates.id", "knowledge_candidates.material_id"],
            ondelete="CASCADE",
            name="fk_knowledge_candidate_sources_candidate_material",
        ),
        UniqueConstraint(
            "candidate_id",
            "material_id",
            "source_reference",
            name="uq_knowledge_candidate_sources_candidate_material_reference",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(nullable=False, index=True)
    material_id: Mapped[int] = mapped_column(nullable=False, index=True)
    source_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    excerpt: Mapped[str] = mapped_column(String(1000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    candidate: Mapped[KnowledgeCandidate] = relationship(back_populates="sources")
