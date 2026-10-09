from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Enum, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, TimestampMixin
from backend.app.models import KnowledgeDifficulty, KnowledgeImportance

if TYPE_CHECKING:
    from backend.app.db.models.course import Course
    from backend.app.db.models.knowledge_source import KnowledgeSource


def _enum_values(enum_type: type[KnowledgeImportance] | type[KnowledgeDifficulty]) -> list[str]:
    return [member.value for member in enum_type]


class KnowledgeNode(TimestampMixin, Base):
    __tablename__ = "knowledge_nodes"
    __table_args__ = (
        UniqueConstraint("course_id", "id", name="uq_knowledge_nodes_course_id_id"),
        Index("ix_knowledge_nodes_course_normalized_name", "course_id", "normalized_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    importance: Mapped[KnowledgeImportance] = mapped_column(
        Enum(
            KnowledgeImportance,
            values_callable=_enum_values,
            native_enum=False,
            create_constraint=True,
            name="knowledge_importance",
        ),
        default=KnowledgeImportance.MEDIUM,
        nullable=False,
    )
    difficulty: Mapped[KnowledgeDifficulty] = mapped_column(
        Enum(
            KnowledgeDifficulty,
            values_callable=_enum_values,
            native_enum=False,
            create_constraint=True,
            name="knowledge_difficulty",
        ),
        default=KnowledgeDifficulty.INTERMEDIATE,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    managed_by_canonicalization: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    course: Mapped[Course] = relationship(back_populates="knowledge_nodes")
    sources: Mapped[list[KnowledgeSource]] = relationship(back_populates="knowledge_node", passive_deletes=True)
