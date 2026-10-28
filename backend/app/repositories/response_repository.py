from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models import Response


class ResponseRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_for_question(self, assessment_question_id: int) -> Response | None:
        return self.session.scalar(select(Response).where(Response.assessment_question_id == assessment_question_id))

    def list_for_assessment(self, assessment_id: int) -> list[Response]:
        statement = (
            select(Response).where(Response.assessment_id == assessment_id).order_by(Response.assessment_question_id)
        )
        return list(self.session.scalars(statement))

    def save_draft(
        self,
        *,
        assessment_id: int,
        assessment_question_id: int,
        answer_payload: dict[str, Any],
        answered_at: datetime,
    ) -> Response:
        response = self.get_for_question(assessment_question_id)
        if response is None:
            response = Response(
                assessment_id=assessment_id,
                assessment_question_id=assessment_question_id,
                answer_payload=answer_payload,
                answered_at=answered_at,
            )
            self.session.add(response)
        else:
            if response.submitted_at is not None:
                raise ValueError("A submitted response cannot be modified.")
            response.answer_payload = answer_payload
            response.answered_at = answered_at
        self.session.flush()
        return response

    def create_submitted(self, response: Response) -> Response:
        self.session.add(response)
        self.session.flush()
        return response
