"""Pseudonymous, rotatable Mini App session identities."""

from __future__ import annotations

import hashlib
import hmac
import secrets


def session_subject_key(application_secret: str, user_id: int) -> str:
    return hmac.new(
        application_secret.encode("utf-8"),
        f"diagnostic-subject:{user_id}".encode("ascii"),
        hashlib.sha256,
    ).hexdigest()


def new_session_generation() -> str:
    return secrets.token_hex(16)


def session_scope(application_secret: str, user_id: int, generation: str) -> str:
    return hmac.new(
        application_secret.encode("utf-8"),
        f"diagnostic-scope:{user_id}:{generation}".encode("ascii"),
        hashlib.sha256,
    ).hexdigest()[:24]
