from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.app.db.models import KnowledgeCanonicalizationRun
from backend.app.models import KnowledgeCanonicalizationStatus


class KnowledgeCanonicalizationRunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, run: KnowledgeCanonicalizationRun) -> KnowledgeCanonicalizationRun:
        self.session.add(run)
        self.session.flush()
        return run

    def get_by_id(self, run_id: int) -> KnowledgeCanonicalizationRun | None:
        return self.session.get(KnowledgeCanonicalizationRun, run_id)

    def get_current_for_course(self, course_id: int) -> KnowledgeCanonicalizationRun | None:
        statement = (
            select(KnowledgeCanonicalizationRun)
            .where(
                KnowledgeCanonicalizationRun.course_id == course_id,
                KnowledgeCanonicalizationRun.status == KnowledgeCanonicalizationStatus.SUCCESS,
                KnowledgeCanonicalizationRun.is_current.is_(True),
            )
            .order_by(KnowledgeCanonicalizationRun.id.desc())
        )
        return self.session.scalar(statement)

    def get_latest_for_course(self, course_id: int) -> KnowledgeCanonicalizationRun | None:
        statement = (
            select(KnowledgeCanonicalizationRun)
            .where(KnowledgeCanonicalizationRun.course_id == course_id)
            .order_by(KnowledgeCanonicalizationRun.id.desc())
        )
        return self.session.scalar(statement)

    def find_current_by_key(
        self,
        course_id: int,
        candidate_snapshot_hash: str,
        prompt_version: str,
        model: str,
        configuration_version: str,
    ) -> KnowledgeCanonicalizationRun | None:
        statement = select(KnowledgeCanonicalizationRun).where(
            KnowledgeCanonicalizationRun.course_id == course_id,
            KnowledgeCanonicalizationRun.candidate_snapshot_hash == candidate_snapshot_hash,
            KnowledgeCanonicalizationRun.prompt_version == prompt_version,
            KnowledgeCanonicalizationRun.model == model,
            KnowledgeCanonicalizationRun.configuration_version == configuration_version,
            KnowledgeCanonicalizationRun.status == KnowledgeCanonicalizationStatus.SUCCESS,
            KnowledgeCanonicalizationRun.is_current.is_(True),
        )
        return self.session.scalar(statement)

    def clear_current(self, course_id: int) -> None:
        self.session.execute(
            update(KnowledgeCanonicalizationRun)
            .where(
                KnowledgeCanonicalizationRun.course_id == course_id,
                KnowledgeCanonicalizationRun.is_current.is_(True),
            )
            .values(is_current=False)
        )
        self.session.flush()

    def save(self, run: KnowledgeCanonicalizationRun) -> KnowledgeCanonicalizationRun:
        self.session.add(run)
        self.session.flush()
        return run
