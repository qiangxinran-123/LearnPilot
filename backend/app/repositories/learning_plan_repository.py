from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.app.db.models import LearningPlan
from backend.app.models import LearningPlanStatus


class LearningPlanRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_current(self, *, user_id: int, course_id: int, for_update: bool = False) -> LearningPlan | None:
        statement = (
            select(LearningPlan)
            .options(selectinload(LearningPlan.tasks))
            .where(
                LearningPlan.user_id == user_id,
                LearningPlan.course_id == course_id,
                LearningPlan.status == LearningPlanStatus.AVAILABLE,
                LearningPlan.active_slot == 1,
            )
        )
        if for_update:
            statement = statement.with_for_update()
        return self.session.scalar(statement)

    def add(self, plan: LearningPlan) -> LearningPlan:
        self.session.add(plan)
        self.session.flush()
        return plan

    def supersede(self, plan: LearningPlan) -> None:
        plan.status = LearningPlanStatus.SUPERSEDED
        plan.active_slot = None
        self.session.flush()
