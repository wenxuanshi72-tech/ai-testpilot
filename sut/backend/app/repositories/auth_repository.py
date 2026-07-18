from __future__ import annotations

from sqlalchemy import select

from sut.backend.app.extensions import db
from sut.backend.app.models import User, UserSession


class AuthRepository:
    def find_user_by_username(self, username: str) -> User | None:
        return db.session.scalar(select(User).where(User.username == username))

    def find_session_by_token_hash(self, token_hash: str) -> UserSession | None:
        return db.session.scalar(select(UserSession).where(UserSession.token_hash == token_hash))

    def add_user(self, user: User) -> None:
        db.session.add(user)

    def add_session(self, user_session: UserSession) -> None:
        db.session.add(user_session)

    def commit(self) -> None:
        db.session.commit()

    def rollback(self) -> None:
        db.session.rollback()
