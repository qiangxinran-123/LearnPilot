from __future__ import annotations

import base64
import binascii
from datetime import datetime, timezone

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from backend.app.core.settings import Settings
from backend.app.db.models import Assessment, KnowledgeNode, LearningSession
from backend.app.models import AssessmentStatus, AssessmentType, LearningSessionStatus
from backend.app.schemas.progress_history import LearningEventType, LearningHistoryEvent, LearningHistoryPage
from backend.app.services.mastery_read_service import MasteryReadError, MasteryReadService


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _decode_cursor(cursor: str) -> tuple[datetime, str, int]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        timestamp, event_type, identifier = raw.split("|")
        at = datetime.fromisoformat(timestamp)
        if at.tzinfo is None or event_type not in {item.value for item in LearningEventType} or int(identifier) <= 0:
            raise ValueError
        return _utc(at), event_type, int(identifier)
    except (ValueError, UnicodeError, binascii.Error) as error:
        raise MasteryReadError("INVALID_HISTORY_CURSOR", "Invalid history cursor.") from error


def _encode_cursor(event: LearningHistoryEvent) -> str:
    identifier = event.id.rsplit("-", 1)[1]
    value = f"{_utc(event.occurred_at).isoformat()}|{event.event_type.value}|{identifier}"
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii")


class LearningHistoryService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.mastery = MasteryReadService(session, settings)

    def history(self, course_id: int, *, limit: int, cursor: str | None) -> LearningHistoryPage:
        # Reuse M5's hidden-course authorization; it does not write or refresh mastery.
        self.mastery.course_mastery(course_id)
        owner_id = self.mastery._require_owner_id()
        boundary = _decode_cursor(cursor) if cursor else None
        events: list[LearningHistoryEvent] = []
        diagnostic = select(Assessment).where(
            Assessment.owner_id == owner_id,
            Assessment.course_id == course_id,
            Assessment.assessment_type == AssessmentType.INITIAL_DIAGNOSTIC,
            Assessment.status == AssessmentStatus.SUBMITTED,
            Assessment.submitted_at.is_not(None),
        )
        sessions = (
            select(LearningSession, KnowledgeNode.name)
            .join(KnowledgeNode, KnowledgeNode.id == LearningSession.target_knowledge_node_id)
            .where(
                LearningSession.user_id == owner_id,
                LearningSession.course_id == course_id,
                LearningSession.status == LearningSessionStatus.COMPLETED,
                LearningSession.completed_at.is_not(None),
            )
        )
        for kind, statement, timestamp, identifier in (
            (LearningEventType.DIAGNOSIS_COMPLETED, diagnostic, Assessment.submitted_at, Assessment.id),
            (LearningEventType.LEARNING_SESSION_COMPLETED, sessions, LearningSession.completed_at, LearningSession.id),
        ):
            if boundary:
                at, previous_kind, previous_id = boundary
                # Ordering is descending by timestamp, event type and source ID.
                tie = identifier < previous_id if kind.value == previous_kind else kind.value < previous_kind
                statement = statement.where(or_(timestamp < at, and_(timestamp == at, tie)))
            rows = self.session.execute(statement.order_by(timestamp.desc(), identifier.desc()).limit(limit + 1)).all()
            for row in rows:
                item = row[0]
                recorded = item.submitted_at if kind == LearningEventType.DIAGNOSIS_COMPLETED else item.completed_at
                assert recorded is not None
                events.append(
                    LearningHistoryEvent(
                        id=f"{kind.value}-{item.id}",
                        event_type=kind,
                        occurred_at=_utc(recorded),
                        course_id=course_id,
                        knowledge_node_id=item.target_knowledge_node_id
                        if kind == LearningEventType.LEARNING_SESSION_COMPLETED
                        else None,
                        knowledge_node_name=row[1] if kind == LearningEventType.LEARNING_SESSION_COMPLETED else None,
                    )
                )
        events.sort(
            key=lambda event: (_utc(event.occurred_at), event.event_type.value, int(event.id.rsplit("-", 1)[1])),
            reverse=True,
        )
        page = events[:limit]
        return LearningHistoryPage(
            course_id=course_id,
            events=page,
            next_cursor=_encode_cursor(page[-1]) if len(events) > limit else None,
        )
