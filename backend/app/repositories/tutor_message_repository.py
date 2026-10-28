from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models import TutorMessage
from backend.app.models import TutorMessageRole


class TutorMessageRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add_all(self, messages: list[TutorMessage]) -> None:
        self.session.add_all(messages)
        self.session.flush()

    def get_request(self, *, session_id: int, idempotency_key: str) -> TutorMessage | None:
        return self.session.scalar(
            select(TutorMessage).where(
                TutorMessage.session_id == session_id,
                TutorMessage.role == TutorMessageRole.USER,
                TutorMessage.idempotency_key == idempotency_key,
            )
        )

    def list_exchange(self, *, session_id: int, exchange_id: str) -> list[TutorMessage]:
        statement = (
            select(TutorMessage)
            .where(TutorMessage.session_id == session_id, TutorMessage.exchange_id == exchange_id)
            .order_by(TutorMessage.id)
        )
        return list(self.session.scalars(statement))

    def list_for_session(self, *, session_id: int) -> list[TutorMessage]:
        statement = (
            select(TutorMessage)
            .where(TutorMessage.session_id == session_id)
            .order_by(TutorMessage.created_at, TutorMessage.id)
        )
        return list(self.session.scalars(statement))

    def list_recent(self, *, session_id: int, limit: int) -> list[TutorMessage]:
        statement = (
            select(TutorMessage)
            .where(TutorMessage.session_id == session_id)
            .order_by(TutorMessage.created_at.desc(), TutorMessage.id.desc())
            .limit(limit)
        )
        return list(reversed(list(self.session.scalars(statement))))


__all__ = ["TutorMessageRepository"]
