from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from sut.backend.app.errors import ApiError
from sut.backend.app.models import User, UserSession
from sut.backend.app.repositories import AuthRepository
from sut.backend.app.security.sessions import (
    generate_public_id,
    generate_session_token,
    hash_session_token,
)
from sut.backend.app.time import as_utc, utc_now
from sut.backend.app.validation import LoginInput, RegistrationInput

DUMMY_PASSWORD_HASH = generate_password_hash("TimingOnly123")


@dataclass(frozen=True)
class AuthenticatedSession:
    user: User
    raw_token: str
    expires_at: datetime


class AuthService:
    def __init__(
        self,
        repository: AuthRepository,
        *,
        absolute_seconds: int,
        idle_seconds: int,
    ) -> None:
        self.repository = repository
        self.absolute_seconds = absolute_seconds
        self.idle_seconds = idle_seconds

    def register(self, registration: RegistrationInput) -> AuthenticatedSession:
        if self.repository.find_user_by_username(registration.username) is not None:
            raise ApiError(409, "USERNAME_EXISTS", "The username is already registered.")

        now = utc_now()
        user = User(
            user_id=generate_public_id("USR"),
            username=registration.username,
            password_hash=generate_password_hash(registration.password),
            created_at=now,
            updated_at=now,
        )
        self.repository.add_user(user)
        try:
            self.repository.commit()
        except IntegrityError as error:
            self.repository.rollback()
            raise ApiError(409, "USERNAME_EXISTS", "The username is already registered.") from error
        return self._create_session(user, now=now)

    def login(self, login: LoginInput) -> AuthenticatedSession:
        user = self.repository.find_user_by_username(login.username)
        candidate_hash = user.password_hash if user is not None else DUMMY_PASSWORD_HASH
        valid_password = check_password_hash(candidate_hash, login.password)
        if user is None or not user.is_active or not valid_password:
            raise ApiError(401, "INVALID_CREDENTIALS", "The username or password is invalid.")
        return self._create_session(user)

    def authenticate(self, raw_token: str | None) -> User | None:
        if not raw_token:
            return None
        user_session = self.repository.find_session_by_token_hash(hash_session_token(raw_token))
        if user_session is None or user_session.revoked_at is not None:
            return None

        now = utc_now()
        absolute_expired = as_utc(user_session.expires_at) <= now
        idle_expired = (
            as_utc(user_session.last_seen_at) + timedelta(seconds=self.idle_seconds) <= now
        )
        if absolute_expired or idle_expired or not user_session.user.is_active:
            if user_session.revoked_at is None:
                user_session.revoked_at = now
                self.repository.commit()
            return None

        user_session.last_seen_at = now
        self.repository.commit()
        return user_session.user

    def logout(self, raw_token: str | None) -> None:
        if not raw_token:
            return
        user_session = self.repository.find_session_by_token_hash(hash_session_token(raw_token))
        if user_session is not None and user_session.revoked_at is None:
            user_session.revoked_at = utc_now()
            self.repository.commit()

    def _create_session(self, user: User, *, now: datetime | None = None) -> AuthenticatedSession:
        issued_at = now or utc_now()
        expires_at = issued_at + timedelta(seconds=self.absolute_seconds)
        raw_token = generate_session_token()
        user_session = UserSession(
            session_id=generate_public_id("SES"),
            user_id=user.id,
            token_hash=hash_session_token(raw_token),
            created_at=issued_at,
            last_seen_at=issued_at,
            expires_at=expires_at,
        )
        self.repository.add_session(user_session)
        self.repository.commit()
        return AuthenticatedSession(user=user, raw_token=raw_token, expires_at=expires_at)
