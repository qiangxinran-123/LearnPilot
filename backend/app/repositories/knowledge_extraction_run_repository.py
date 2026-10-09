from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.app.db.models import KnowledgeExtractionRun, MaterialContent
from backend.app.models import KnowledgeExtractionStatus


class KnowledgeExtractionRunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, run: KnowledgeExtractionRun) -> KnowledgeExtractionRun:
        self.session.add(run)
        self.session.flush()
        return run

    def get_by_id(self, run_id: int) -> KnowledgeExtractionRun | None:
        return self.session.get(KnowledgeExtractionRun, run_id)

    def get_current_for_material(self, material_id: int) -> KnowledgeExtractionRun | None:
        statement = (
            select(KnowledgeExtractionRun)
            .where(
                KnowledgeExtractionRun.material_id == material_id,
                KnowledgeExtractionRun.status == KnowledgeExtractionStatus.SUCCESS,
                KnowledgeExtractionRun.is_current.is_(True),
            )
            .order_by(KnowledgeExtractionRun.id.desc())
        )
        return self.session.scalar(statement)

    def get_latest_for_material(self, material_id: int) -> KnowledgeExtractionRun | None:
        statement = (
            select(KnowledgeExtractionRun)
            .where(KnowledgeExtractionRun.material_id == material_id)
            .order_by(KnowledgeExtractionRun.id.desc())
        )
        return self.session.scalar(statement)

    def list_current_for_course(self, course_id: int) -> list[KnowledgeExtractionRun]:
        statement = (
            select(KnowledgeExtractionRun)
            .join(MaterialContent, MaterialContent.material_id == KnowledgeExtractionRun.material_id)
            .where(
                KnowledgeExtractionRun.course_id == course_id,
                KnowledgeExtractionRun.status == KnowledgeExtractionStatus.SUCCESS,
                KnowledgeExtractionRun.is_current.is_(True),
                KnowledgeExtractionRun.material_content_hash == MaterialContent.content_hash,
            )
            .order_by(KnowledgeExtractionRun.material_id, KnowledgeExtractionRun.id)
        )
        return list(self.session.scalars(statement))

    def find_current_by_key(
        self,
        material_id: int,
        material_content_hash: str,
        prompt_version: str,
        model: str,
    ) -> KnowledgeExtractionRun | None:
        statement = select(KnowledgeExtractionRun).where(
            KnowledgeExtractionRun.material_id == material_id,
            KnowledgeExtractionRun.material_content_hash == material_content_hash,
            KnowledgeExtractionRun.prompt_version == prompt_version,
            KnowledgeExtractionRun.model == model,
            KnowledgeExtractionRun.status == KnowledgeExtractionStatus.SUCCESS,
            KnowledgeExtractionRun.is_current.is_(True),
        )
        return self.session.scalar(statement)

    def clear_current(self, material_id: int) -> None:
        self.session.execute(
            update(KnowledgeExtractionRun)
            .where(
                KnowledgeExtractionRun.material_id == material_id,
                KnowledgeExtractionRun.is_current.is_(True),
            )
            .values(is_current=False)
        )
        self.session.flush()

    def save(self, run: KnowledgeExtractionRun) -> KnowledgeExtractionRun:
        self.session.add(run)
        self.session.flush()
        return run
