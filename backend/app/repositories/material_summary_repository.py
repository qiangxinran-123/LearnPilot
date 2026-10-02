from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models import MaterialSummary


class MaterialSummaryRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_for_material(self, material_id: int) -> MaterialSummary | None:
        return self.session.scalar(select(MaterialSummary).where(MaterialSummary.material_id == material_id))

    def save(self, summary: MaterialSummary) -> MaterialSummary:
        self.session.add(summary)
        self.session.flush()
        return summary
