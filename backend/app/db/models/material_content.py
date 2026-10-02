from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from backend.app.db.models.material import Material


class MaterialContent(TimestampMixin, Base):
    __tablename__ = "material_contents"
    __table_args__ = (UniqueConstraint("material_id", name="uq_material_contents_material_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id", ondelete="CASCADE"), nullable=False, index=True)
    plain_text: Mapped[str] = mapped_column(Text().with_variant(LONGTEXT(), "mysql"), nullable=False)
    segments: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    parser_name: Mapped[str] = mapped_column(String(80), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(32), nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    material: Mapped[Material] = relationship(back_populates="content")
