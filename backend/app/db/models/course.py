from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from backend.app.db.models.knowledge_node import KnowledgeNode
    from backend.app.db.models.material import Material
    from backend.app.db.models.user import User


class Course(TimestampMixin, Base):
    __tablename__ = "courses"
    __table_args__ = (UniqueConstraint("legacy_key", name="uq_courses_legacy_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    category: Mapped[str | None] = mapped_column(String(120), nullable=True)
    learning_goal: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    legacy_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    owner: Mapped[User] = relationship(back_populates="courses")
    materials: Mapped[list[Material]] = relationship(back_populates="course", cascade="all, delete-orphan")
    knowledge_nodes: Mapped[list[KnowledgeNode]] = relationship(back_populates="course", cascade="all, delete-orphan")
