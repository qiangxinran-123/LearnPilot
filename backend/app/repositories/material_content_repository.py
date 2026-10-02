from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models import MaterialContent


class MaterialContentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_for_material(self, material_id: int) -> MaterialContent | None:
        return self.session.scalar(select(MaterialContent).where(MaterialContent.material_id == material_id))

    def save(self, content: MaterialContent) -> MaterialContent:
        self.session.add(content)
        self.session.flush()
        return content
