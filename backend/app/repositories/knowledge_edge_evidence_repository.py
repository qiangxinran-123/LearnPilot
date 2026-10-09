from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models import KnowledgeEdgeEvidence


class KnowledgeEdgeEvidenceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, evidence: KnowledgeEdgeEvidence) -> KnowledgeEdgeEvidence:
        self.session.add(evidence)
        self.session.flush()
        return evidence

    def list_for_edge(self, edge_id: int) -> list[KnowledgeEdgeEvidence]:
        statement = (
            select(KnowledgeEdgeEvidence)
            .where(KnowledgeEdgeEvidence.knowledge_edge_id == edge_id)
            .order_by(KnowledgeEdgeEvidence.id)
        )
        return list(self.session.scalars(statement))

    def list_for_edges(self, edge_ids: list[int]) -> list[KnowledgeEdgeEvidence]:
        if not edge_ids:
            return []
        statement = (
            select(KnowledgeEdgeEvidence)
            .where(KnowledgeEdgeEvidence.knowledge_edge_id.in_(edge_ids))
            .order_by(KnowledgeEdgeEvidence.knowledge_edge_id, KnowledgeEdgeEvidence.id)
        )
        return list(self.session.scalars(statement))
