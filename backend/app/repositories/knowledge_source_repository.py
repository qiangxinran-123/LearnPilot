from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.app.db.models import KnowledgeSource


class KnowledgeSourceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, source: KnowledgeSource) -> KnowledgeSource:
        self.session.add(source)
        self.session.flush()
        return source

    def list_for_node(self, node_id: int) -> list[KnowledgeSource]:
        statement = (
            select(KnowledgeSource).where(KnowledgeSource.knowledge_node_id == node_id).order_by(KnowledgeSource.id)
        )
        return list(self.session.scalars(statement))

    def delete_by_material(self, material_id: int) -> int:
        result = self.session.execute(delete(KnowledgeSource).where(KnowledgeSource.material_id == material_id))
        self.session.flush()
        return result.rowcount or 0

    def exists(self, node_id: int, material_id: int, source_reference: str) -> bool:
        statement = select(KnowledgeSource.id).where(
            KnowledgeSource.knowledge_node_id == node_id,
            KnowledgeSource.material_id == material_id,
            KnowledgeSource.source_reference == source_reference,
        )
        return self.session.scalar(statement) is not None
