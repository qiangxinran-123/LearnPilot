from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.db.models import Course, Material


class CourseRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_all(self) -> list[Course]:
        return list(self.session.scalars(select(Course).order_by(Course.id)))

    def list_for_owner(self, owner_id: int) -> list[Course]:
        statement = select(Course).where(Course.owner_id == owner_id).order_by(Course.id)
        return list(self.session.scalars(statement))

    def list_with_material_counts(self, owner_id: int) -> list[tuple[Course, int]]:
        statement = (
            select(Course, func.count(Material.id))
            .outerjoin(Material, Material.course_id == Course.id)
            .where(Course.owner_id == owner_id)
            .group_by(Course.id)
            .order_by(Course.id)
        )
        return [(course, count) for course, count in self.session.execute(statement).all()]

    def get_by_id(self, course_id: int) -> Course | None:
        return self.session.get(Course, course_id)

    def get_for_owner(self, course_id: int, owner_id: int) -> Course | None:
        statement = select(Course).where(Course.id == course_id, Course.owner_id == owner_id)
        return self.session.scalar(statement)

    def get_by_legacy_key(self, legacy_key: str) -> Course | None:
        return self.session.scalar(select(Course).where(Course.legacy_key == legacy_key))

    def add(self, course: Course) -> Course:
        self.session.add(course)
        self.session.flush()
        return course

    def delete(self, course: Course) -> None:
        self.session.delete(course)
        self.session.flush()
