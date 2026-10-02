from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models import StudyCard


class StudyCardRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_for_material(self, material_id: int) -> list[StudyCard]:
        statement = select(StudyCard).where(StudyCard.material_id == material_id).order_by(StudyCard.order_index)
        return list(self.session.scalars(statement))

    def replace_for_material(self, material_id: int, cards: list[StudyCard]) -> list[StudyCard]:
        existing = self.list_for_material(material_id)
        for current, replacement in zip(existing, cards, strict=False):
            current.question = replacement.question
            current.answer = replacement.answer
            current.knowledge_hint = replacement.knowledge_hint
            current.source_reference = replacement.source_reference
            current.order_index = replacement.order_index
            current.model_provider = replacement.model_provider
            current.model_name = replacement.model_name
            current.prompt_version = replacement.prompt_version
        for replacement in cards[len(existing) :]:
            self.session.add(replacement)
        for obsolete in existing[len(cards) :]:
            self.session.delete(obsolete)
        self.session.flush()
        return self.list_for_material(material_id)
