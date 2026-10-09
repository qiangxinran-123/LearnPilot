from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.app.db.models import KnowledgeRelationshipRun
from backend.app.models import KnowledgeRelationshipStatus


class KnowledgeRelationshipRunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, run: KnowledgeRelationshipRun) -> KnowledgeRelationshipRun:
        self.session.add(run)
        self.session.flush()
        return run

    def get_by_id(self, run_id: int) -> KnowledgeRelationshipRun | None:
        return self.session.get(KnowledgeRelationshipRun, run_id)

    def get_current_for_course(self, course_id: int) -> KnowledgeRelationshipRun | None:
        statement = (
            select(KnowledgeRelationshipRun)
            .where(
                KnowledgeRelationshipRun.course_id == course_id,
                KnowledgeRelationshipRun.status == KnowledgeRelationshipStatus.SUCCESS,
                KnowledgeRelationshipRun.is_current.is_(True),
            )
            .order_by(KnowledgeRelationshipRun.id.desc())
        )
        return self.session.scalar(statement)

    def get_latest_for_course(self, course_id: int) -> KnowledgeRelationshipRun | None:
        statement = (
            select(KnowledgeRelationshipRun)
            .where(KnowledgeRelationshipRun.course_id == course_id)
            .order_by(KnowledgeRelationshipRun.id.desc())
        )
        return self.session.scalar(statement)

    def find_current_by_key(
        self,
        course_id: int,
        knowledge_snapshot_hash: str,
        prompt_version: str,
        model: str,
    ) -> KnowledgeRelationshipRun | None:
        statement = select(KnowledgeRelationshipRun).where(
            KnowledgeRelationshipRun.course_id == course_id,
            KnowledgeRelationshipRun.knowledge_snapshot_hash == knowledge_snapshot_hash,
            KnowledgeRelationshipRun.prompt_version == prompt_version,
            KnowledgeRelationshipRun.model == model,
            KnowledgeRelationshipRun.status == KnowledgeRelationshipStatus.SUCCESS,
            KnowledgeRelationshipRun.is_current.is_(True),
        )
        return self.session.scalar(statement)

    def clear_current(self, course_id: int) -> None:
        self.session.execute(
            update(KnowledgeRelationshipRun)
            .where(
                KnowledgeRelationshipRun.course_id == course_id,
                KnowledgeRelationshipRun.is_current.is_(True),
            )
            .values(is_current=False)
        )
        self.session.flush()

    def save(self, run: KnowledgeRelationshipRun) -> KnowledgeRelationshipRun:
        self.session.add(run)
        self.session.flush()
        return run
