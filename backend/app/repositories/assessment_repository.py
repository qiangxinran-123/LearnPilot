from __future__ import annotations

from sqlalchemy import select, update
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

    def get_for_owner(self, assessment_id: int, owner_id: int, *, load_history: bool = False) -> Assessment | None:
        statement = select(Assessment).where(Assessment.id == assessment_id, Assessment.owner_id == owner_id)
        if load_history:
            statement = statement.options(
                selectinload(Assessment.questions).selectinload(AssessmentQuestion.response),
                selectinload(Assessment.responses),
            )
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
