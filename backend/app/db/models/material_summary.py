from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from backend.app.db.models.material import Material


class MaterialSummary(TimestampMixin, Base):
    __tablename__ = "material_summaries"
    __table_args__ = (UniqueConstraint("material_id", name="uq_material_summaries_material_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id", ondelete="CASCADE"), nullable=False, index=True)
    overview: Mapped[str] = mapped_column(Text, nullable=False)
    key_concepts: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    important_points: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    common_mistakes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    review_suggestions: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    model_provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model_name: Mapped[str] = mapped_column(String(160), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(80), nullable=False)

    material: Mapped[Material] = relationship(back_populates="summary_artifact")
