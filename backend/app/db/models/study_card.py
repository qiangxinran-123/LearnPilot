from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from backend.app.db.models.material import Material


class StudyCard(TimestampMixin, Base):
    __tablename__ = "study_cards"
    __table_args__ = (UniqueConstraint("material_id", "order_index", name="uq_study_cards_material_order"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id", ondelete="CASCADE"), nullable=False, index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    knowledge_hint: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    model_provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model_name: Mapped[str] = mapped_column(String(160), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(80), nullable=False)

    material: Mapped[Material] = relationship(back_populates="study_cards")
