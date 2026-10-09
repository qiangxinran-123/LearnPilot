from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKeyConstraint, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base
from backend.app.models import KnowledgeResolutionType

if TYPE_CHECKING:
    from backend.app.db.models.knowledge_canonicalization_run import KnowledgeCanonicalizationRun


def _resolution_values(enum_type: type[KnowledgeResolutionType]) -> list[str]:
    return [member.value for member in enum_type]


class KnowledgeCandidateResolution(Base):
    __tablename__ = "knowledge_candidate_resolutions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["canonicalization_run_id", "course_id"],
            ["knowledge_canonicalization_runs.id", "knowledge_canonicalization_runs.course_id"],
            ondelete="CASCADE",
            name="fk_knowledge_candidate_resolutions_run_course",
        ),
        ForeignKeyConstraint(
            ["course_id", "knowledge_node_id"],
            ["knowledge_nodes.course_id", "knowledge_nodes.id"],
            ondelete="CASCADE",
            name="fk_knowledge_candidate_resolutions_node_course",
        ),
        ForeignKeyConstraint(
            ["candidate_id", "course_id"],
            ["knowledge_candidates.id", "knowledge_candidates.course_id"],
            ondelete="CASCADE",
            name="fk_knowledge_candidate_resolutions_candidate_course",
        ),
        UniqueConstraint(
            "canonicalization_run_id",
            "candidate_id",
            name="uq_knowledge_candidate_resolutions_run_candidate",
        ),
        Index("ix_knowledge_candidate_resolutions_node_id", "knowledge_node_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    canonicalization_run_id: Mapped[int] = mapped_column(nullable=False, index=True)
    course_id: Mapped[int] = mapped_column(nullable=False)
    candidate_id: Mapped[int] = mapped_column(nullable=False, index=True)
    knowledge_node_id: Mapped[int] = mapped_column(nullable=False)
    resolution_type: Mapped[KnowledgeResolutionType] = mapped_column(
        Enum(
            KnowledgeResolutionType,
            values_callable=_resolution_values,
            native_enum=False,
            create_constraint=True,
            name="knowledge_resolution_type",
        ),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    canonicalization_run: Mapped[KnowledgeCanonicalizationRun] = relationship(back_populates="resolutions")
