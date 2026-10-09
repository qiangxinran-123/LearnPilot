from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKeyConstraint, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base
from backend.app.models import KnowledgeDifficulty, KnowledgeImportance

if TYPE_CHECKING:
    from backend.app.db.models.knowledge_candidate_source import KnowledgeCandidateSource
    from backend.app.db.models.knowledge_extraction_run import KnowledgeExtractionRun


def _enum_values(enum_type: type[KnowledgeImportance] | type[KnowledgeDifficulty]) -> list[str]:
    return [member.value for member in enum_type]


class KnowledgeCandidate(Base):
    __tablename__ = "knowledge_candidates"
    __table_args__ = (
        ForeignKeyConstraint(
            ["extraction_run_id", "course_id", "material_id"],
            [
                "knowledge_extraction_runs.id",
                "knowledge_extraction_runs.course_id",
                "knowledge_extraction_runs.material_id",
            ],
            ondelete="CASCADE",
            name="fk_knowledge_candidates_run_context",
        ),
        UniqueConstraint(
            "extraction_run_id",
            "normalized_name",
            name="uq_knowledge_candidates_run_normalized_name",
        ),
        UniqueConstraint("id", "material_id", name="uq_knowledge_candidates_id_material"),
        UniqueConstraint("id", "course_id", name="uq_knowledge_candidates_id_course"),
        Index("ix_knowledge_candidates_course_material", "course_id", "material_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    extraction_run_id: Mapped[int] = mapped_column(nullable=False, index=True)
    course_id: Mapped[int] = mapped_column(nullable=False)
    material_id: Mapped[int] = mapped_column(nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), nullable=False)
    importance: Mapped[KnowledgeImportance] = mapped_column(
        Enum(
            KnowledgeImportance,
            values_callable=_enum_values,
            native_enum=False,
            create_constraint=True,
            name="knowledge_candidate_importance",
        ),
        nullable=False,
    )
    difficulty: Mapped[KnowledgeDifficulty] = mapped_column(
        Enum(
            KnowledgeDifficulty,
            values_callable=_enum_values,
            native_enum=False,
            create_constraint=True,
            name="knowledge_candidate_difficulty",
        ),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    extraction_run: Mapped[KnowledgeExtractionRun] = relationship(back_populates="candidates")
    sources: Mapped[list[KnowledgeCandidateSource]] = relationship(
        back_populates="candidate",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="KnowledgeCandidateSource.id",
    )
