from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.app.db.models import KnowledgeCandidate


class KnowledgeCandidateRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, candidate: KnowledgeCandidate) -> KnowledgeCandidate:
        self.session.add(candidate)
        self.session.flush()
        return candidate

    def list_for_run(self, extraction_run_id: int) -> list[KnowledgeCandidate]:
        statement = (
            select(KnowledgeCandidate)
            .options(selectinload(KnowledgeCandidate.sources))
            .where(KnowledgeCandidate.extraction_run_id == extraction_run_id)
            .order_by(KnowledgeCandidate.id)
        )
        return list(self.session.scalars(statement))

    def list_for_runs(self, extraction_run_ids: list[int]) -> list[KnowledgeCandidate]:
        if not extraction_run_ids:
            return []
        statement = (
            select(KnowledgeCandidate)
            .options(selectinload(KnowledgeCandidate.sources))
            .where(KnowledgeCandidate.extraction_run_id.in_(extraction_run_ids))
            .order_by(KnowledgeCandidate.id)
        )
        return list(self.session.scalars(statement))
