from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sut.backend.app.extensions import db
from sut.backend.app.time import utc_now

if TYPE_CHECKING:
    from sut.backend.app.models.user_session import UserSession


class User(db.Model):  # type: ignore[name-defined, misc]
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    sessions: Mapped[list[UserSession]] = relationship(
        back_populates="user", cascade="save-update, merge"
    )
