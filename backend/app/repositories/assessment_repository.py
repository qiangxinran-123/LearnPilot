from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, selectinload

from backend.app.db.models import Assessment, AssessmentQuestion
from backend.app.models import AssessmentStatus


class AssessmentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, assessment: Assessment) -> Assessment:
        self.session.add(assessment)
        self.session.flush()
        return assessment

    def get_for_owner(
        self,
        assessment_id: int,
        owner_id: int,
        *,
        load_history: bool = False,
        for_update: bool = False,
    ) -> Assessment | None:
        statement = select(Assessment).where(Assessment.id == assessment_id, Assessment.owner_id == owner_id)
        if load_history:
            statement = statement.options(
                selectinload(Assessment.questions).selectinload(AssessmentQuestion.response),
                selectinload(Assessment.responses),
            )
        if for_update:
            statement = statement.with_for_update()
        return self.session.scalar(statement)

    def list_for_course_owner(self, course_id: int, owner_id: int) -> list[Assessment]:
        statement = (
            select(Assessment)
            .where(Assessment.course_id == course_id, Assessment.owner_id == owner_id)
            .order_by(Assessment.id)
        )
        return list(self.session.scalars(statement))

    def add_question_snapshot(self, assessment_question: AssessmentQuestion) -> AssessmentQuestion:
        self.session.add(assessment_question)
        self.session.flush()
        return assessment_question

    def delete(self, assessment: Assessment) -> None:
        self.session.delete(assessment)
        self.session.flush()

    def get_question(self, assessment_id: int, assessment_question_id: int) -> AssessmentQuestion | None:
        statement = select(AssessmentQuestion).where(
            AssessmentQuestion.id == assessment_question_id,
            AssessmentQuestion.assessment_id == assessment_id,
        )
        return self.session.scalar(statement)

    def list_questions(self, assessment_id: int) -> list[AssessmentQuestion]:
        statement = (
            select(AssessmentQuestion)
            .where(AssessmentQuestion.assessment_id == assessment_id)
            .order_by(AssessmentQuestion.order_index)
        )
        return list(self.session.scalars(statement))

    def question_exposure_counts(self, *, owner_id: int, question_ids: list[int]) -> dict[int, int]:
        if not question_ids:
            return {}
        statement = (
            select(AssessmentQuestion.question_id, func.count(AssessmentQuestion.id))
            .join(Assessment, Assessment.id == AssessmentQuestion.assessment_id)
            .where(Assessment.owner_id == owner_id, AssessmentQuestion.question_id.in_(question_ids))
            .group_by(AssessmentQuestion.question_id)
        )
        return {int(question_id): int(count) for question_id, count in self.session.execute(statement)}

    def compare_and_set_status(
        self, assessment_id: int, expected: AssessmentStatus, target: AssessmentStatus, **values: object
    ) -> bool:
        result = self.session.execute(
            update(Assessment)
            .where(Assessment.id == assessment_id, Assessment.status == expected)
            .values(status=target, **values)
        )
        self.session.flush()
        return (result.rowcount or 0) == 1
