from __future__ import annotations

import hashlib
import secrets


def generate_session_token() -> str:
    return secrets.token_urlsafe(48)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_public_id(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(12)}"
