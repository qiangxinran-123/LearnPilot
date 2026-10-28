from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from backend.app.db.models import LearningPlan, LearningSession, LearningSessionTaskState
from backend.app.models import LearningPlanStatus, LearningSessionStatus, LearningSessionTaskPhase


class LearningSessionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def _detail_options():
        return (
            joinedload(LearningSession.course),
            joinedload(LearningSession.target_knowledge_node),
            selectinload(LearningSession.tasks),
        )

    def get_owned(self, *, session_id: int, user_id: int, for_update: bool = False) -> LearningSession | None:
        statement = (
            select(LearningSession)
            .options(*self._detail_options())
            .where(LearningSession.id == session_id, LearningSession.user_id == user_id)
        )
        if for_update:
            statement = statement.with_for_update()
        return self.session.scalar(statement)

    def get_active_for_target(
        self, *, user_id: int, course_id: int, target_node_id: int, for_update: bool = False
    ) -> LearningSession | None:
        statement = (
            select(LearningSession)
            .options(*self._detail_options())
            .where(
                LearningSession.user_id == user_id,
                LearningSession.course_id == course_id,
                LearningSession.target_knowledge_node_id == target_node_id,
                LearningSession.status.in_((LearningSessionStatus.CREATED, LearningSessionStatus.IN_PROGRESS)),
                LearningSession.active_slot == 1,
            )
        )
        if for_update:
            statement = statement.with_for_update()
        return self.session.scalar(statement)

    def get_active_for_course(self, *, user_id: int, course_id: int) -> LearningSession | None:
        statement = (
            select(LearningSession)
            .options(*self._detail_options())
            .where(
                LearningSession.user_id == user_id,
                LearningSession.course_id == course_id,
                LearningSession.status.in_((LearningSessionStatus.CREATED, LearningSessionStatus.IN_PROGRESS)),
                LearningSession.active_slot == 1,
            )
            .order_by(LearningSession.updated_at.desc(), LearningSession.id.desc())
        )
        return self.session.scalars(statement).first()

    def get_available_plan(self, *, plan_id: int, user_id: int, course_id: int) -> LearningPlan | None:
        statement = (
            select(LearningPlan)
            .options(selectinload(LearningPlan.tasks))
            .where(
                LearningPlan.id == plan_id,
                LearningPlan.user_id == user_id,
                LearningPlan.course_id == course_id,
                LearningPlan.status == LearningPlanStatus.AVAILABLE,
                LearningPlan.active_slot == 1,
            )
        )
        return self.session.scalar(statement)

    def add(self, learning_session: LearningSession) -> LearningSession:
        self.session.add(learning_session)
        self.session.flush()
        return learning_session

    def task_for_phase(self, *, session_id: int, phase: LearningSessionTaskPhase) -> LearningSessionTaskState | None:
        return self.session.scalar(
            select(LearningSessionTaskState).where(
                LearningSessionTaskState.session_id == session_id,
                LearningSessionTaskState.phase == phase,
            )
        )
