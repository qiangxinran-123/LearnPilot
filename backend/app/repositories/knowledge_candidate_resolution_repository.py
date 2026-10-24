from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models import KnowledgeCandidateResolution


class KnowledgeCandidateResolutionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, resolution: KnowledgeCandidateResolution) -> KnowledgeCandidateResolution:
        self.session.add(resolution)
        self.session.flush()
        return resolution

    def list_for_run(self, canonicalization_run_id: int) -> list[KnowledgeCandidateResolution]:
        statement = (
            select(KnowledgeCandidateResolution)
            .where(KnowledgeCandidateResolution.canonicalization_run_id == canonicalization_run_id)
            .order_by(KnowledgeCandidateResolution.id)
        )
        return list(self.session.scalars(statement))

    def latest_by_candidate_ids(self, candidate_ids: set[int]) -> dict[int, KnowledgeCandidateResolution]:
        """Return the most recent published resolution known for each candidate."""

        if not candidate_ids:
            return {}
        statement = (
            select(KnowledgeCandidateResolution)
            .where(KnowledgeCandidateResolution.candidate_id.in_(candidate_ids))
            .order_by(
                KnowledgeCandidateResolution.candidate_id,
                KnowledgeCandidateResolution.created_at.desc(),
                KnowledgeCandidateResolution.id.desc(),
            )
        )
        latest: dict[int, KnowledgeCandidateResolution] = {}
        for resolution in self.session.scalars(statement):
            latest.setdefault(resolution.candidate_id, resolution)
        return latest
