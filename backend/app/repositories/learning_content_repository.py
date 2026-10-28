from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models import KnowledgeSource, Material, MaterialContent


class LearningContentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_direct_sources(
        self, *, course_id: int, knowledge_node_id: int
    ) -> list[tuple[KnowledgeSource, Material, MaterialContent]]:
        statement = (
            select(KnowledgeSource, Material, MaterialContent)
            .join(Material, Material.id == KnowledgeSource.material_id)
            .join(MaterialContent, MaterialContent.material_id == Material.id)
            .where(
                KnowledgeSource.knowledge_node_id == knowledge_node_id,
                Material.course_id == course_id,
                Material.extraction_status.in_(("SUCCESS", "EXTRACTED")),
            )
            .order_by(KnowledgeSource.id, Material.id)
        )
        return list(self.session.execute(statement).tuples())

    def list_course_contents(self, *, course_id: int) -> list[tuple[Material, MaterialContent]]:
        statement = (
            select(Material, MaterialContent)
            .join(MaterialContent, MaterialContent.material_id == Material.id)
            .where(
                Material.course_id == course_id,
                Material.extraction_status.in_(("SUCCESS", "EXTRACTED")),
            )
            .order_by(Material.id, MaterialContent.id)
        )
        return list(self.session.execute(statement).tuples())


__all__ = ["LearningContentRepository"]
