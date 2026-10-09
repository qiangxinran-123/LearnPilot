from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base
from backend.app.models import KnowledgeEdgeEvidenceType


def _evidence_values(enum_type: type[KnowledgeEdgeEvidenceType]) -> list[str]:
    return [member.value for member in enum_type]


class KnowledgeEdgeEvidence(Base):
    __tablename__ = "knowledge_edge_evidences"
    __table_args__ = (
        ForeignKeyConstraint(
            ["knowledge_edge_id", "course_id"],
            ["knowledge_edges.id", "knowledge_edges.course_id"],
            ondelete="CASCADE",
            name="fk_knowledge_edge_evidences_edge_course",
        ),
        Index("ix_knowledge_edge_evidences_edge_id", "knowledge_edge_id"),
        Index("ix_knowledge_edge_evidences_course_id", "course_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    knowledge_edge_id: Mapped[int] = mapped_column(Integer, nullable=False)
    course_id: Mapped[int] = mapped_column(Integer, nullable=False)
    material_id: Mapped[int | None] = mapped_column(ForeignKey("materials.id", ondelete="CASCADE"), nullable=True)
    source_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    excerpt: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    evidence_type: Mapped[KnowledgeEdgeEvidenceType] = mapped_column(
        Enum(
            KnowledgeEdgeEvidenceType,
            values_callable=_evidence_values,
            native_enum=False,
            create_constraint=True,
            name="knowledge_edge_evidence_type",
        ),
        nullable=False,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
