from __future__ import annotations

from sqlalchemy import CheckConstraint, Enum, ForeignKey, ForeignKeyConstraint, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, TimestampMixin
from backend.app.models import KnowledgeRelationType


def _relation_values(enum_type: type[KnowledgeRelationType]) -> list[str]:
    return [member.value for member in enum_type]


class KnowledgeEdge(TimestampMixin, Base):
    __tablename__ = "knowledge_edges"
    __table_args__ = (
        CheckConstraint("source_node_id <> target_node_id", name="ck_knowledge_edges_no_self_edge"),
        UniqueConstraint(
            "course_id",
            "source_node_id",
            "target_node_id",
            "relation_type",
            name="uq_knowledge_edges_course_source_target_relation",
        ),
        UniqueConstraint("id", "course_id", name="uq_knowledge_edges_id_course"),
        ForeignKeyConstraint(
            ["course_id", "source_node_id"],
            ["knowledge_nodes.course_id", "knowledge_nodes.id"],
            ondelete="CASCADE",
            name="fk_knowledge_edges_source_in_course",
        ),
        ForeignKeyConstraint(
            ["course_id", "target_node_id"],
            ["knowledge_nodes.course_id", "knowledge_nodes.id"],
            ondelete="CASCADE",
            name="fk_knowledge_edges_target_in_course",
        ),
        ForeignKeyConstraint(
            ["course_id", "relationship_run_id"],
            ["knowledge_relationship_runs.course_id", "knowledge_relationship_runs.id"],
            ondelete="CASCADE",
            name="fk_knowledge_edges_relationship_run_course",
        ),
        Index("ix_knowledge_edges_source_node_id", "source_node_id"),
        Index("ix_knowledge_edges_target_node_id", "target_node_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    source_node_id: Mapped[int] = mapped_column(nullable=False)
    target_node_id: Mapped[int] = mapped_column(nullable=False)
    relation_type: Mapped[KnowledgeRelationType] = mapped_column(
        Enum(
            KnowledgeRelationType,
            values_callable=_relation_values,
            native_enum=False,
            create_constraint=True,
            name="knowledge_relation_type",
        ),
        nullable=False,
    )
    relationship_run_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
