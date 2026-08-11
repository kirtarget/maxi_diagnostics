"""Constant-time HTTP Basic authentication for diagnostic administration."""

from __future__ import annotations

import base64
import binascii
import hashlib
import secrets

from fastapi import HTTPException, Request, status


_CHALLENGE = {"WWW-Authenticate": 'Basic realm="diagnostic-admin"'}
_MAX_AUTHORIZATION_LENGTH = 1_024
_MAX_BASIC_TOKEN_LENGTH = 520
_MAX_DECODED_LENGTH = 385


def _parse_credentials(authorization: str | None) -> tuple[str, str]:
    if (
        authorization is None
        or len(authorization) > _MAX_AUTHORIZATION_LENGTH
        or len(authorization) < 7
        or authorization[:6].lower() != "basic "
    ):
        return "", ""
    token = authorization[6:]
    if not token or len(token) > _MAX_BASIC_TOKEN_LENGTH:
        return "", ""
    try:
        decoded_bytes = base64.b64decode(token, validate=True)
    except (binascii.Error, ValueError):
        return "", ""
    if len(decoded_bytes) > _MAX_DECODED_LENGTH:
        return "", ""
    try:
        decoded = decoded_bytes.decode("ascii")
    except UnicodeDecodeError:
        return "", ""
    if ":" not in decoded:
        return "", ""
    username, password = decoded.split(":", 1)
    if (
        not 1 <= len(username) <= 128
        or not 1 <= len(password) <= 256
        or username != username.strip()
        or ":" in username
        or not all(" " <= character <= "~" for character in decoded)
    ):
        return "", ""
    return username, password


def require_admin(
    request: Request,
) -> str:
    settings = request.app.state.settings
    supplied_username, supplied_password = _parse_credentials(
        request.headers.get("authorization")
    )
    username_matches = secrets.compare_digest(
        hashlib.sha256(supplied_username.encode("utf-8")).digest(),
        hashlib.sha256(settings.admin_username.encode("utf-8")).digest(),
    )
    password_matches = secrets.compare_digest(
        hashlib.sha256(supplied_password.encode("utf-8")).digest(),
        hashlib.sha256(settings.admin_password.encode("utf-8")).digest(),
    )
    if not (username_matches & password_matches):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers=_CHALLENGE,
        )
    return supplied_username
