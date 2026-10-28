from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.settings import Settings, get_settings
from backend.app.db.models import LearningSession, LearningSessionTaskState
from backend.app.db.session import get_db
from backend.app.models import (
    LearningSessionStatus,
    LearningSessionTaskPhase,
    LearningSessionTaskStatus,
    LearningTaskType,
)
from backend.app.repositories import CourseRepository, KnowledgeNodeRepository, UserRepository
from backend.app.repositories.learning_session_repository import LearningSessionRepository
from backend.app.schemas.learning_session import (
    ActiveLearningSessionResponse,
    LearningSessionCreate,
    LearningSessionRead,
    LearningSessionTaskRead,
    LearningSessionTaskUpdate,
)

SESSION_CONTRACT_VERSION = "learning_session_v1"
PHASES = (
    LearningSessionTaskPhase.CONCEPT_LEARNING,
    LearningSessionTaskPhase.GUIDED_EXAMPLE,
    LearningSessionTaskPhase.ADAPTIVE_PRACTICE,
)
SOURCE_TASK_TYPES = {
    LearningSessionTaskPhase.CONCEPT_LEARNING: LearningTaskType.CONCEPT_REVIEW,
    LearningSessionTaskPhase.GUIDED_EXAMPLE: LearningTaskType.EXAMPLE_WALKTHROUGH,
    LearningSessionTaskPhase.ADAPTIVE_PRACTICE: LearningTaskType.TARGETED_PRACTICE,
}


class LearningSessionError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class LearningSessionService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.sessions = LearningSessionRepository(session)
        self.users = UserRepository(session)
        self.courses = CourseRepository(session)
        self.nodes = KnowledgeNodeRepository(session)

    def create_for_configured_user(self, payload: LearningSessionCreate) -> LearningSessionRead:
        user_id = self._configured_user_id()
        target_node_id = payload.target_knowledge_node_id or 0
        try:
            with self.session.begin():
                course = self.courses.get_for_owner(payload.course_id, user_id)
                if course is None:
                    raise LearningSessionError("COURSE_NOT_FOUND", "Course not found.")

                plan = None
                if payload.learning_plan_id is not None:
                    plan = self.sessions.get_available_plan(
                        plan_id=payload.learning_plan_id,
                        user_id=user_id,
                        course_id=payload.course_id,
                    )
                    if plan is None:
                        raise LearningSessionError(
                            "LEARNING_PLAN_NOT_AVAILABLE",
                            "The learning plan is not available for this course.",
                        )
                    target_node_id = plan.target_node_id
                else:
                    assert payload.target_knowledge_node_id is not None
                    target_node_id = payload.target_knowledge_node_id

                node = self.nodes.get_by_id(target_node_id)
                if node is None or node.course_id != course.id:
                    raise LearningSessionError(
                        "KNOWLEDGE_NODE_NOT_FOUND",
                        "Knowledge node not found in this course.",
                    )
                if not node.is_active:
                    raise LearningSessionError(
                        "KNOWLEDGE_NODE_INACTIVE",
                        "The target knowledge node is no longer active.",
                    )

                current = self.sessions.get_active_for_target(
                    user_id=user_id,
                    course_id=course.id,
                    target_node_id=node.id,
                    for_update=True,
                )
                if current is not None:
                    return _read_session(current, reused=True)

                source_tasks = {task.task_type: task.id for task in (plan.tasks if plan else [])}
                learning_session = LearningSession(
                    user_id=user_id,
                    course_id=course.id,
                    target_knowledge_node_id=node.id,
                    source_learning_plan_id=plan.id if plan else None,
                    status=LearningSessionStatus.CREATED,
                    active_slot=1,
                    session_contract_version=SESSION_CONTRACT_VERSION,
                    tasks=[
                        LearningSessionTaskState(
                            phase=phase,
                            order_index=index,
                            status=LearningSessionTaskStatus.NOT_STARTED,
                            source_learning_task_id=source_tasks.get(SOURCE_TASK_TYPES[phase]),
                            progress={},
                        )
                        for index, phase in enumerate(PHASES)
                    ],
                )
                self.sessions.add(learning_session)
                return _read_session(learning_session)
        except IntegrityError as error:
            self.session.rollback()
            with self.session.begin():
                winner = self.sessions.get_active_for_target(
                    user_id=user_id,
                    course_id=payload.course_id,
                    target_node_id=target_node_id,
                )
                if winner is not None:
                    return _read_session(winner, reused=True)
            raise LearningSessionError(
                "LEARNING_SESSION_CONFLICT",
                "The learning session changed concurrently; retry the request.",
            ) from error

    def get_for_configured_user(self, session_id: int) -> LearningSessionRead:
        user_id = self._configured_user_id()
        with self.session.begin():
            learning_session = self._require_owned(session_id, user_id)
            return _read_session(learning_session)

    def get_active_for_configured_user(self, course_id: int) -> ActiveLearningSessionResponse:
        user_id = self._configured_user_id()
        with self.session.begin():
            if self.courses.get_for_owner(course_id, user_id) is None:
                raise LearningSessionError("COURSE_NOT_FOUND", "Course not found.")
            learning_session = self.sessions.get_active_for_course(user_id=user_id, course_id=course_id)
            return ActiveLearningSessionResponse(
                session=_read_session(learning_session) if learning_session is not None else None
            )

    def update_task_for_configured_user(
        self,
        *,
        session_id: int,
        phase: LearningSessionTaskPhase,
        payload: LearningSessionTaskUpdate,
    ) -> LearningSessionRead:
        user_id = self._configured_user_id()
        with self.session.begin():
            learning_session = self._require_owned(session_id, user_id, for_update=True)
            if not learning_session.target_knowledge_node.is_active:
                raise LearningSessionError(
                    "KNOWLEDGE_NODE_INACTIVE",
                    "The target knowledge node is no longer active.",
                )
            if learning_session.status in (
                LearningSessionStatus.CANCELLED,
                LearningSessionStatus.COMPLETED,
            ):
                raise LearningSessionError("SESSION_NOT_WRITABLE", "This learning session is read-only.")
            task = next((item for item in learning_session.tasks if item.phase == phase), None)
            if task is None:
                raise LearningSessionError("SESSION_TASK_NOT_FOUND", "Session task not found.")
            if phase == LearningSessionTaskPhase.ADAPTIVE_PRACTICE:
                if payload.status == task.status:
                    return _read_session(learning_session)
                raise LearningSessionError(
                    "TASK_PHASE_NOT_AVAILABLE",
                    "Adaptive practice becomes available in M7-4.",
                )
            if payload.status == task.status:
                return _read_session(learning_session)

            allowed = {
                LearningSessionTaskStatus.NOT_STARTED: LearningSessionTaskStatus.IN_PROGRESS,
                LearningSessionTaskStatus.IN_PROGRESS: LearningSessionTaskStatus.COMPLETED,
            }
            if allowed.get(task.status) != payload.status:
                raise LearningSessionError(
                    "INVALID_TASK_TRANSITION",
                    f"Cannot move task from {task.status.value} to {payload.status.value}.",
                )
            if any(
                previous.status != LearningSessionTaskStatus.COMPLETED
                for previous in learning_session.tasks
                if previous.order_index < task.order_index
            ):
                raise LearningSessionError("TASK_ORDER_VIOLATION", "Complete earlier learning phases first.")

            now = datetime.now(timezone.utc)
            task.status = payload.status
            if payload.status == LearningSessionTaskStatus.IN_PROGRESS:
                task.started_at = task.started_at or now
                if learning_session.status == LearningSessionStatus.CREATED:
                    learning_session.status = LearningSessionStatus.IN_PROGRESS
                    learning_session.started_at = learning_session.started_at or now
            else:
                task.completed_at = task.completed_at or now
            self.session.flush()
            return _read_session(learning_session)

    def cancel_for_configured_user(self, session_id: int) -> LearningSessionRead:
        user_id = self._configured_user_id()
        with self.session.begin():
            learning_session = self._require_owned(session_id, user_id, for_update=True)
            if learning_session.status == LearningSessionStatus.CANCELLED:
                return _read_session(learning_session)
            if learning_session.status == LearningSessionStatus.COMPLETED:
                raise LearningSessionError(
                    "SESSION_NOT_CANCELLABLE", "A completed learning session cannot be cancelled."
                )
            learning_session.status = LearningSessionStatus.CANCELLED
            learning_session.active_slot = None
            learning_session.cancelled_at = datetime.now(timezone.utc)
            self.session.flush()
            return _read_session(learning_session)

    def _configured_user_id(self) -> int:
        with self.session.begin():
            user = self.users.get_by_email(self.settings.legacy_bootstrap_user)
            if user is None:
                raise LearningSessionError("USER_NOT_FOUND", "User not found.")
            return user.id

    def _require_owned(self, session_id: int, user_id: int, *, for_update: bool = False) -> LearningSession:
        learning_session = self.sessions.get_owned(session_id=session_id, user_id=user_id, for_update=for_update)
        if learning_session is None:
            raise LearningSessionError("SESSION_NOT_FOUND", "Learning session not found.")
        return learning_session


def _read_session(learning_session: LearningSession, *, reused: bool = False) -> LearningSessionRead:
    return LearningSessionRead(
        session_id=learning_session.id,
        user_id=learning_session.user_id,
        course_id=learning_session.course_id,
        course_name=learning_session.course.name,
        target_knowledge_node_id=learning_session.target_knowledge_node_id,
        target_knowledge_node_name=learning_session.target_knowledge_node.name,
        source_learning_plan_id=learning_session.source_learning_plan_id,
        practice_assessment_id=learning_session.practice_assessment_id,
        status=learning_session.status,
        session_contract_version=learning_session.session_contract_version,
        completion_summary=learning_session.completion_summary,
        recommendation_refresh_status=learning_session.recommendation_refresh_status,
        tasks=[
            LearningSessionTaskRead(
                task_id=task.id,
                phase=task.phase,
                order_index=task.order_index,
                status=task.status,
                source_learning_task_id=task.source_learning_task_id,
                progress=task.progress,
                started_at=task.started_at,
                completed_at=task.completed_at,
                created_at=task.created_at,
                updated_at=task.updated_at,
            )
            for task in sorted(learning_session.tasks, key=lambda item: (item.order_index, item.id or 0))
        ],
        started_at=learning_session.started_at,
        completed_at=learning_session.completed_at,
        cancelled_at=learning_session.cancelled_at,
        created_at=learning_session.created_at,
        updated_at=learning_session.updated_at,
        reused=reused,
    )


def get_learning_session_service(
    session: Session = Depends(get_db), settings: Settings = Depends(get_settings)
) -> LearningSessionService:
    return LearningSessionService(session, settings)


__all__ = [
    "LearningSessionError",
    "LearningSessionService",
    "get_learning_session_service",
]
