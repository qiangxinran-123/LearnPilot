from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models import KnowledgeCandidateSource


class KnowledgeCandidateSourceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, source: KnowledgeCandidateSource) -> KnowledgeCandidateSource:
        self.session.add(source)
        self.session.flush()
        return source

    def list_for_candidate(self, candidate_id: int) -> list[KnowledgeCandidateSource]:
        statement = (
            select(KnowledgeCandidateSource)
            .where(KnowledgeCandidateSource.candidate_id == candidate_id)
            .order_by(KnowledgeCandidateSource.id)
        )
        return list(self.session.scalars(statement))
