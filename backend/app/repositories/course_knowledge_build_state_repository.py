from __future__ import annotations

from datetime import datetime

from sqlalchemy import update
from sqlalchemy.orm import Session

from backend.app.db.models import CourseKnowledgeBuildState


class CourseKnowledgeBuildStateRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_for_course(self, course_id: int) -> CourseKnowledgeBuildState | None:
        return self.session.get(CourseKnowledgeBuildState, course_id)

    def create(self, state: CourseKnowledgeBuildState) -> CourseKnowledgeBuildState:
        self.session.add(state)
        self.session.flush()
        return state

    def claim(
        self,
        course_id: int,
        *,
        material_snapshot_hash: str,
        checkpoint_json: str,
        started_at: datetime,
    ) -> bool:
        result = self.session.execute(
            update(CourseKnowledgeBuildState)
            .where(
                CourseKnowledgeBuildState.course_id == course_id,
                CourseKnowledgeBuildState.status != "running",
            )
            .values(
                job_id=CourseKnowledgeBuildState.job_id + 1,
                status="running",
                stage="queued",
                error_code=None,
                error_message=None,
                last_added_node_count=0,
                last_reused_node_count=0,
                requested_material_snapshot_hash=material_snapshot_hash,
                checkpoint_json=checkpoint_json,
                started_at=started_at,
                heartbeat_at=started_at,
                completed_at=None,
            )
        )
        self.session.flush()
        return result.rowcount == 1

    def save(self, state: CourseKnowledgeBuildState) -> CourseKnowledgeBuildState:
        self.session.add(state)
        self.session.flush()
        return state
