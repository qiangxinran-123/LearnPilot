from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKeyConstraint, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base
from backend.app.models import KnowledgeRelationRole

if TYPE_CHECKING:
    from backend.app.db.models.knowledge_node import KnowledgeNode
    from backend.app.db.models.question import Question


def _enum_values(enum_type: type[KnowledgeRelationRole]) -> list[str]:
    return [member.value for member in enum_type]


class QuestionKnowledgeNode(Base):
    __tablename__ = "question_knowledge_nodes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["course_id", "question_id"],
            ["questions.course_id", "questions.id"],
            ondelete="CASCADE",
            name="fk_question_knowledge_nodes_question_course",
        ),
        ForeignKeyConstraint(
            ["course_id", "knowledge_node_id"],
            ["knowledge_nodes.course_id", "knowledge_nodes.id"],
            ondelete="CASCADE",
            name="fk_question_knowledge_nodes_node_course",
        ),
        UniqueConstraint("question_id", "knowledge_node_id", name="uq_question_knowledge_nodes_question_node"),
        Index("ix_question_knowledge_nodes_course_node", "course_id", "knowledge_node_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(nullable=False)
    question_id: Mapped[int] = mapped_column(nullable=False, index=True)
    knowledge_node_id: Mapped[int] = mapped_column(nullable=False, index=True)
    relation_role: Mapped[KnowledgeRelationRole] = mapped_column(
        Enum(
            KnowledgeRelationRole,
            values_callable=_enum_values,
            native_enum=False,
            create_constraint=True,
            name="question_knowledge_relation_role",
        ),
        nullable=False,
    )

    question: Mapped[Question] = relationship(back_populates="knowledge_links")
    knowledge_node: Mapped[KnowledgeNode] = relationship(overlaps="knowledge_links,question")
