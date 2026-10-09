from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.app.db.models import KnowledgeNode


class KnowledgeNodeRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, node: KnowledgeNode) -> KnowledgeNode:
        self.session.add(node)
        self.session.flush()
        return node

    def get_by_id(self, node_id: int) -> KnowledgeNode | None:
        return self.session.get(KnowledgeNode, node_id)

    def list_by_course(self, course_id: int) -> list[KnowledgeNode]:
        statement = (
            select(KnowledgeNode)
            .where(
                KnowledgeNode.course_id == course_id,
                KnowledgeNode.is_active.is_(True),
            )
            .order_by(KnowledgeNode.id)
        )
        return list(self.session.scalars(statement))

    def list_all_by_course(self, course_id: int) -> list[KnowledgeNode]:
        statement = select(KnowledgeNode).where(KnowledgeNode.course_id == course_id).order_by(KnowledgeNode.id)
        return list(self.session.scalars(statement))

    def update(self, node: KnowledgeNode) -> KnowledgeNode:
        self.session.add(node)
        self.session.flush()
        return node

    def delete(self, node: KnowledgeNode) -> None:
        self.session.delete(node)
        self.session.flush()

    def find_by_normalized_name(self, course_id: int, normalized_name: str) -> KnowledgeNode | None:
        statement = select(KnowledgeNode).where(
            KnowledgeNode.course_id == course_id,
            KnowledgeNode.normalized_name == normalized_name,
        )
        return self.session.scalar(statement)

    def deactivate_managed_except(self, course_id: int, active_node_ids: set[int]) -> None:
        statement = update(KnowledgeNode).where(
            KnowledgeNode.course_id == course_id,
            KnowledgeNode.managed_by_canonicalization.is_(True),
        )
        if active_node_ids:
            statement = statement.where(KnowledgeNode.id.not_in(active_node_ids))
        self.session.execute(statement.values(is_active=False))
        self.session.flush()
