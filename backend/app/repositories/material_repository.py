from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.app.db.models import Course, Material


class MaterialRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_for_course(self, course_id: int) -> list[Material]:
        statement = select(Material).where(Material.course_id == course_id).order_by(Material.id)
        return list(self.session.scalars(statement))

    def list_for_owned_course(self, course_id: int, owner_id: int) -> list[Material]:
        statement = (
            select(Material)
            .join(Course, Course.id == Material.course_id)
            .where(Material.course_id == course_id, Course.owner_id == owner_id)
            .order_by(Material.id)
        )
        return list(self.session.scalars(statement))

    def get_by_id(self, material_id: int) -> Material | None:
        return self.session.get(Material, material_id)

    def get_for_owner(self, material_id: int, owner_id: int) -> Material | None:
        statement = (
            select(Material)
            .join(Course, Course.id == Material.course_id)
            .where(Material.id == material_id, Course.owner_id == owner_id)
        )
        return self.session.scalar(statement)

    def get_by_legacy_key(self, legacy_key: str) -> Material | None:
        return self.session.scalar(select(Material).where(Material.legacy_key == legacy_key))

    def add(self, material: Material) -> Material:
        self.session.add(material)
        self.session.flush()
        return material

    def delete(self, material: Material) -> None:
        self.session.delete(material)
        self.session.flush()

    def search(self, keyword: str, owner_id: int, course_id: int | None = None) -> list[Material]:
        pattern = f"%{keyword.casefold()}%"
        fields = (
            Material.title,
            Material.summary,
            Material.original_filename,
            Material.text_preview,
            Material.ai_summary,
        )
        statement = (
            select(Material)
            .join(Course, Course.id == Material.course_id)
            .where(Course.owner_id == owner_id, or_(*(field.ilike(pattern) for field in fields)))
        )
        if course_id is not None:
            statement = statement.where(Material.course_id == course_id)
        return list(self.session.scalars(statement.order_by(Material.id)))
