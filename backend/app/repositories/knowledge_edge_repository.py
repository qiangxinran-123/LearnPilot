from __future__ import annotations

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.orm import Session, aliased

from backend.app.db.models import KnowledgeEdge, KnowledgeRelationshipRun
from backend.app.models import KnowledgeRelationshipStatus, KnowledgeRelationType


class KnowledgeEdgeRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, edge: KnowledgeEdge) -> KnowledgeEdge:
        self.session.add(edge)
        self.session.flush()
        return edge

    def list_by_course(self, course_id: int) -> list[KnowledgeEdge]:
        statement = select(KnowledgeEdge).where(KnowledgeEdge.course_id == course_id).order_by(KnowledgeEdge.id)
        return list(self.session.scalars(statement))

    def list_for_node(self, node_id: int) -> list[KnowledgeEdge]:
        statement = (
            select(KnowledgeEdge)
            .where(
                or_(
                    KnowledgeEdge.source_node_id == node_id,
                    KnowledgeEdge.target_node_id == node_id,
                )
            )
            .order_by(KnowledgeEdge.id)
        )
        return list(self.session.scalars(statement))

    def list_manual_by_course(self, course_id: int) -> list[KnowledgeEdge]:
        statement = (
            select(KnowledgeEdge)
            .where(
                KnowledgeEdge.course_id == course_id,
                KnowledgeEdge.relationship_run_id.is_(None),
            )
            .order_by(KnowledgeEdge.id)
        )
        return list(self.session.scalars(statement))

    def list_for_run(self, relationship_run_id: int) -> list[KnowledgeEdge]:
        statement = (
            select(KnowledgeEdge)
            .where(KnowledgeEdge.relationship_run_id == relationship_run_id)
            .order_by(KnowledgeEdge.id)
        )
        return list(self.session.scalars(statement))

    def list_current_by_course(self, course_id: int) -> list[KnowledgeEdge]:
        run = aliased(KnowledgeRelationshipRun)
        statement = (
            select(KnowledgeEdge)
            .outerjoin(run, KnowledgeEdge.relationship_run_id == run.id)
            .where(
                KnowledgeEdge.course_id == course_id,
                or_(
                    KnowledgeEdge.relationship_run_id.is_(None),
                    and_(
                        run.status == KnowledgeRelationshipStatus.SUCCESS,
                        run.is_current.is_(True),
                    ),
                ),
            )
            .order_by(KnowledgeEdge.id)
        )
        return list(self.session.scalars(statement))

    def list_current_for_node(self, node_id: int) -> list[KnowledgeEdge]:
        run = aliased(KnowledgeRelationshipRun)
        statement = (
            select(KnowledgeEdge)
            .outerjoin(run, KnowledgeEdge.relationship_run_id == run.id)
            .where(
                or_(KnowledgeEdge.source_node_id == node_id, KnowledgeEdge.target_node_id == node_id),
                or_(
                    KnowledgeEdge.relationship_run_id.is_(None),
                    and_(
                        run.status == KnowledgeRelationshipStatus.SUCCESS,
                        run.is_current.is_(True),
                    ),
                ),
            )
            .order_by(KnowledgeEdge.id)
        )
        return list(self.session.scalars(statement))

    def delete_generated_by_course(self, course_id: int) -> int:
        result = self.session.execute(
            delete(KnowledgeEdge).where(
                KnowledgeEdge.course_id == course_id,
                KnowledgeEdge.relationship_run_id.is_not(None),
            )
        )
        self.session.flush()
        return result.rowcount or 0

    def delete(self, edge: KnowledgeEdge) -> None:
        self.session.delete(edge)
        self.session.flush()

    def exists(
        self,
        course_id: int,
        source_node_id: int,
        target_node_id: int,
        relation_type: KnowledgeRelationType,
    ) -> bool:
        statement = select(KnowledgeEdge.id).where(
            KnowledgeEdge.course_id == course_id,
            KnowledgeEdge.source_node_id == source_node_id,
            KnowledgeEdge.target_node_id == target_node_id,
            KnowledgeEdge.relation_type == relation_type,
        )
        return self.session.scalar(statement) is not None
