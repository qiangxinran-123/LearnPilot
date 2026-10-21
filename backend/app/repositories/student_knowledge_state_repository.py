from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models import StudentKnowledgeState


class StudentKnowledgeStateRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, *, user_id: int, course_id: int, knowledge_node_id: int) -> StudentKnowledgeState | None:
        statement = select(StudentKnowledgeState).where(
            StudentKnowledgeState.user_id == user_id,
            StudentKnowledgeState.course_id == course_id,
            StudentKnowledgeState.knowledge_node_id == knowledge_node_id,
        )
        return self.session.scalar(statement)

    def list_by_course_and_user(self, *, user_id: int, course_id: int) -> list[StudentKnowledgeState]:
        statement = (
            select(StudentKnowledgeState)
            .where(
                StudentKnowledgeState.user_id == user_id,
                StudentKnowledgeState.course_id == course_id,
            )
            .order_by(StudentKnowledgeState.knowledge_node_id)
        )
        return list(self.session.scalars(statement))

    def save(self, state: StudentKnowledgeState) -> StudentKnowledgeState:
        self.session.add(state)
        self.session.flush()
        return state
