from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from backend.app.db.models.course import Course
    from backend.app.db.models.knowledge_source import KnowledgeSource
    from backend.app.db.models.material_content import MaterialContent
    from backend.app.db.models.material_summary import MaterialSummary
    from backend.app.db.models.study_card import StudyCard


class Material(TimestampMixin, Base):
    __tablename__ = "materials"
    __table_args__ = (
        UniqueConstraint("storage_key", name="uq_materials_storage_key"),
        UniqueConstraint("legacy_key", name="uq_materials_legacy_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    material_type: Mapped[str] = mapped_column(String(50), default="document", nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    storage_status: Mapped[str] = mapped_column(String(32), default="NOT_STORED", nullable=False)
    media_type: Mapped[str | None] = mapped_column(String(127), nullable=True)
    extension: Mapped[str | None] = mapped_column(String(16), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    text_extracted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    text_preview: Mapped[str] = mapped_column(Text, default="", nullable=False)
    text_length: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    extraction_status: Mapped[str] = mapped_column(String(32), default="NOT_REQUESTED", nullable=False)
    extraction_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    extraction_error_message: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Retained for M1 compatibility. M2 reads durable AI artifacts from dedicated tables.
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_generated: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    summary_method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    summary_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cards: Mapped[list[dict[str, object]] | None] = mapped_column(JSON, nullable=True)
    cards_generated: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    cards_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cards_method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    legacy_key: Mapped[str | None] = mapped_column(String(255), nullable=True)

    course: Mapped[Course] = relationship(back_populates="materials")
    content: Mapped[MaterialContent | None] = relationship(
        back_populates="material", cascade="all, delete-orphan", uselist=False
    )
    summary_artifact: Mapped[MaterialSummary | None] = relationship(
        back_populates="material", cascade="all, delete-orphan", uselist=False
    )
    study_cards: Mapped[list[StudyCard]] = relationship(
        back_populates="material", cascade="all, delete-orphan", order_by="StudyCard.order_index"
    )
    knowledge_sources: Mapped[list[KnowledgeSource]] = relationship(back_populates="material", passive_deletes=True)
