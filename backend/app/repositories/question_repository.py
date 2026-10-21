from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.app.db.models import Course, Question, QuestionKnowledgeNode
from backend.app.models import KnowledgeRelationRole, QuestionValidationStatus


class QuestionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, question: Question) -> Question:
        self.session.add(question)
        self.session.flush()
        return question

    def add_knowledge_link(self, link: QuestionKnowledgeNode) -> QuestionKnowledgeNode:
        self.session.add(link)
        self.session.flush()
        return link

    def get_for_owner(self, question_id: int, owner_id: int) -> Question | None:
        statement = (
            select(Question)
            .join(Course, Course.id == Question.course_id)
            .where(Question.id == question_id, Course.owner_id == owner_id)
            .options(selectinload(Question.knowledge_links).selectinload(QuestionKnowledgeNode.knowledge_node))
        )
        return self.session.scalar(statement)

    def get_for_course(self, question_id: int, course_id: int) -> Question | None:
        statement = (
            select(Question)
            .where(Question.id == question_id, Question.course_id == course_id)
            .options(selectinload(Question.knowledge_links).selectinload(QuestionKnowledgeNode.knowledge_node))
        )
        return self.session.scalar(statement)

    def list_for_course_owner(self, course_id: int, owner_id: int) -> list[Question]:
        statement = (
            select(Question)
            .join(Course, Course.id == Question.course_id)
            .where(Question.course_id == course_id, Course.owner_id == owner_id)
            .order_by(Question.id)
        )
        return list(self.session.scalars(statement))

    def list_for_primary_node(self, course_id: int, knowledge_node_id: int) -> list[Question]:
        statement = (
            select(Question)
            .join(QuestionKnowledgeNode, QuestionKnowledgeNode.question_id == Question.id)
            .where(
                Question.course_id == course_id,
                QuestionKnowledgeNode.knowledge_node_id == knowledge_node_id,
                QuestionKnowledgeNode.relation_role == KnowledgeRelationRole.PRIMARY,
            )
            .order_by(Question.id)
        )
        return list(self.session.scalars(statement))

    def list_validated_for_course(self, course_id: int) -> list[Question]:
        statement = (
            select(Question)
            .where(
                Question.course_id == course_id,
                Question.validation_status == QuestionValidationStatus.VALIDATED,
            )
            .options(selectinload(Question.knowledge_links).selectinload(QuestionKnowledgeNode.knowledge_node))
            .order_by(Question.id)
        )
        return list(self.session.scalars(statement))

    def delete(self, question: Question) -> None:
        self.session.delete(question)
        self.session.flush()
