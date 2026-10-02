from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base

if TYPE_CHECKING:
    from backend.app.db.models.knowledge_node import KnowledgeNode
    from backend.app.db.models.material import Material


class KnowledgeSource(Base):
    __tablename__ = "knowledge_sources"
    __table_args__ = (
        UniqueConstraint(
            "knowledge_node_id",
            "material_id",
            "source_reference",
            name="uq_knowledge_sources_node_material_reference",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    knowledge_node_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id", ondelete="CASCADE"), nullable=False, index=True)
    source_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    excerpt: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    knowledge_node: Mapped[KnowledgeNode] = relationship(back_populates="sources")
    material: Mapped[Material] = relationship(back_populates="knowledge_sources")
