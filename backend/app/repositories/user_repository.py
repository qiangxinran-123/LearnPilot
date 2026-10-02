from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models import User


class UserRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_email(self, email: str) -> User | None:
        return self.session.scalar(select(User).where(User.email == email))

    def add(self, user: User) -> User:
        self.session.add(user)
        self.session.flush()
        return user
