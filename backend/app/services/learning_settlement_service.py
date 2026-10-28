from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import Depends
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from backend.app.core.settings import Settings, get_settings
from backend.app.db.models import Assessment, Course, KnowledgeNode, LearningSession
from backend.app.db.session import get_db
from backend.app.models import (
    AssessmentStatus,
    AssessmentType,
    LearningSessionStatus,
    LearningSessionTaskStatus,
    RecommendationRefreshStatus,
)
from backend.app.repositories import LearningEvidenceRepository, StudentKnowledgeStateRepository, UserRepository
from backend.app.repositories.learning_session_repository import LearningSessionRepository
from backend.app.services.diagnostic_evidence_ingestion import DiagnosticEvidenceExtractor
from backend.app.services.learning_evidence_service import LearningEvidenceService
from backend.app.services.learning_plan_service import LearningPlanService
from backend.app.services.learning_session_service import LearningSessionError, _read_session
from backend.app.services.mastery_read_service import is_persisted_mastery_state_current
from backend.app.services.mastery_service import MasteryService

logger = logging.getLogger(__name__)


class LearningSettlementService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.sessions = LearningSessionRepository(session)
        self.evidence = LearningEvidenceRepository(session)
        self.states = StudentKnowledgeStateRepository(session)

    def complete_for_configured_user(self, session_id: int):
        try:
            with self.session.begin():
                user = UserRepository(self.session).get_by_email(self.settings.legacy_bootstrap_user)
                if user is None:
                    raise LearningSessionError("USER_NOT_FOUND", "User not found.")
                user_id = user.id
                item = self.sessions.get_owned(session_id=session_id, user_id=user_id, for_update=True)
                if item is None or item.course.owner_id != user_id:
                    raise LearningSessionError("SESSION_NOT_FOUND", "Learning session not found.")
                if item.status == LearningSessionStatus.COMPLETED:
                    course_id = item.course_id
                else:
                    if item.status != LearningSessionStatus.IN_PROGRESS:
                        raise LearningSessionError("SESSION_NOT_WRITABLE", "This learning session cannot be completed.")
                    # A conditional write serializes SQLite as well as databases supporting FOR UPDATE.
                    won = self.session.execute(
                        update(LearningSession)
                        .where(
                            LearningSession.id == session_id,
                            LearningSession.user_id == user_id,
                            LearningSession.status == LearningSessionStatus.IN_PROGRESS,
                        )
                        .values(status=LearningSessionStatus.COMPLETED, active_slot=None)
                        .execution_options(synchronize_session=False)
                    ).rowcount
                    if won != 1:
                        raise LearningSessionError("LEARNING_SESSION_CONFLICT", "Session changed; retry.")
                    # Serialize separate sessions in the same course before reading and updating node mastery.
                    self.session.scalar(select(Course).where(Course.id == item.course_id).with_for_update())
                    if (
                        item.target_knowledge_node.course_id != item.course_id
                        or not item.target_knowledge_node.is_active
                        or any(task.status != LearningSessionTaskStatus.COMPLETED for task in item.tasks)
                    ):
                        raise LearningSessionError("SESSION_NOT_READY", "All learning tasks must be complete.")
                    assessment = self.session.get(Assessment, item.practice_assessment_id)
                    if (
                        assessment is None
                        or assessment.owner_id != user_id
                        or assessment.course_id != item.course_id
                        or assessment.assessment_type != AssessmentType.PRACTICE
                        or assessment.status != AssessmentStatus.SUBMITTED
                    ):
                        raise LearningSessionError("PRACTICE_NOT_READY", "A submitted practice is required.")
                    plan = DiagnosticEvidenceExtractor(self.session).extract_assessment(
                        assessment.id,
                        expected_user_id=user_id,
                        expected_course_id=item.course_id,
                        in_transaction=True,
                    )
                    if plan.issues or not plan.candidates:
                        raise LearningSessionError("PRACTICE_NOT_READY", "Practice has invalid or missing scores.")
                    by_question: dict[int, list] = {}
                    for candidate in plan.candidates:
                        by_question.setdefault(candidate.source_question_snapshot_id, []).append(candidate)
                    if any(
                        not any(c.current_knowledge_node_id == item.target_knowledge_node_id for c in candidates)
                        for candidates in by_question.values()
                    ):
                        raise LearningSessionError("PRACTICE_SCOPE_MISMATCH", "Practice target does not match session.")
                    node_ids = sorted(
                        {c.current_knowledge_node_id for c in plan.candidates if c.current_knowledge_node_id}
                    )
                    before = {}
                    for node_id in node_ids:
                        state = self.states.get(user_id=user_id, course_id=item.course_id, knowledge_node_id=node_id)
                        rows = self.evidence.list_for_current_node(
                            user_id=user_id, course_id=item.course_id, knowledge_node_id=node_id
                        )
                        before[node_id] = (
                            float(state.mastery_score)
                            if state is not None
                            and state.mastery_score is not None
                            and is_persisted_mastery_state_current(node_id=node_id, state=state, rows=rows)
                            else None
                        )
                    evidence_ids = []
                    for candidate in plan.candidates:
                        existing = self.evidence.get_by_identity(
                            source_type=candidate.source_type,
                            source_question_snapshot_id=candidate.source_question_snapshot_id,
                            historical_knowledge_node_ref=candidate.historical_knowledge_node_ref,
                            evidence_schema_version=candidate.evidence_schema_version,
                        )
                        if existing is not None and (
                            existing.source_response_id != candidate.source_response_id
                            or existing.user_id != candidate.user_id
                            or existing.course_id != candidate.course_id
                            or existing.normalized_score != candidate.normalized_score
                            or existing.attribution_weight != candidate.attribution_weight
                        ):
                            raise LearningSessionError("PRACTICE_SCOPE_MISMATCH", "Conflicting practice evidence.")
                        row = existing or LearningEvidenceService(self.session).create(candidate, in_transaction=True)
                        evidence_ids.append(row.id)
                    changes = []
                    for node_id in node_ids:
                        result = (
                            MasteryService(self.session)
                            .refresh_state(
                                user_id=user_id,
                                course_id=item.course_id,
                                knowledge_node_id=node_id,
                                in_transaction=True,
                            )
                            .state
                        )
                        after = float(result.mastery_score) if result.mastery_score is not None else None
                        changes.append(
                            {
                                "knowledge_node_id": node_id,
                                "before": before[node_id],
                                "after": after,
                                "delta": round(after - before[node_id], 2)
                                if after is not None and before[node_id] is not None
                                else None,
                                "confidence": result.confidence_level.value,
                                "calculated_at": result.calculated_at.isoformat(),
                            }
                        )
                    responses = [q.response for q in assessment.questions]
                    correct = sum(bool(response.is_correct) for response in responses if response is not None)
                    total = len(responses)
                    item.status = LearningSessionStatus.COMPLETED
                    item.active_slot = None
                    item.completed_at = datetime.now(timezone.utc)
                    item.recommendation_refresh_status = RecommendationRefreshStatus.PENDING
                    item.completion_summary = {
                        "practice_summary": {
                            "total_questions": total,
                            "correct_answers": correct,
                            "accuracy": correct / total,
                        },
                        "mastery_changes": changes,
                        "evidence_ids": evidence_ids,
                        "recommendation": None,
                    }
                    course_id = item.course_id
                    self.session.flush()
            # Reload committed timestamps consistently on SQLite before the M6 context reads them.
            self.session.expire_all()
            self._refresh_recommendation(session_id, user_id, course_id)
            with self.session.begin():
                item = self.sessions.get_owned(session_id=session_id, user_id=user_id)
                if item is None:
                    raise LearningSessionError("SESSION_NOT_FOUND", "Learning session not found.")
                return _read_session(item)
        except (IntegrityError, OperationalError) as error:
            self.session.rollback()
            raise LearningSessionError("LEARNING_SESSION_CONFLICT", "Session changed; retry safely.") from error

    def _refresh_recommendation(self, session_id: int, user_id: int, course_id: int) -> None:
        with self.session.begin():
            item = self.sessions.get_owned(session_id=session_id, user_id=user_id)
            if item is None or item.recommendation_refresh_status == RecommendationRefreshStatus.SUCCEEDED:
                return
        try:
            result = LearningPlanService(self.session, self.settings).generate(user_id=user_id, course_id=course_id)
            with self.session.begin():
                item = self.sessions.get_owned(session_id=session_id, user_id=user_id, for_update=True)
                if item is None or item.recommendation_refresh_status == RecommendationRefreshStatus.SUCCEEDED:
                    return
                summary = dict(item.completion_summary or {})
                recommendation = None
                if result.plan is not None:
                    node = self.session.get(KnowledgeNode, result.plan.target_node_id)
                    recommendation = {
                        "knowledge_node_id": result.plan.target_node_id,
                        "title": node.name if node is not None else "",
                        "reason_codes": [code.value for code in result.plan.reason_codes],
                        "description": result.plan.tasks[0].description,
                        "plan_id": result.plan.plan_id,
                    }
                summary["recommendation"] = recommendation
                item.completion_summary = summary
                item.recommendation_refresh_status = RecommendationRefreshStatus.SUCCEEDED
        except Exception:
            self.session.rollback()
            logger.exception("Recommendation refresh failed for learning session %s", session_id)
            with self.session.begin():
                item = self.sessions.get_owned(session_id=session_id, user_id=user_id, for_update=True)
                if item is not None and item.recommendation_refresh_status != RecommendationRefreshStatus.SUCCEEDED:
                    item.recommendation_refresh_status = RecommendationRefreshStatus.FAILED


def get_learning_settlement_service(
    session: Session = Depends(get_db), settings: Settings = Depends(get_settings)
) -> LearningSettlementService:
    return LearningSettlementService(session, settings)
