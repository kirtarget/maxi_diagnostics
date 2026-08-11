"""Shared request authentication helpers."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request

from diagnostic.auth import validate_init_data


def telegram_user(request: Request, init_data: str) -> dict[str, Any]:
    try:
        payload = validate_init_data(init_data, request.app.state.settings.bot_token)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="invalid_init_data") from exc
    return payload["user"]
