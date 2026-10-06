"""Shared request authentication helpers."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request

from diagnostic.auth import validate_init_data
from diagnostic.card_auth import card_user_id, verify_card_ticket

from .models import ApiRequest


def request_user(request: Request, body: ApiRequest) -> dict[str, Any]:
    try:
        if body.card_ticket is not None:
            card_id = verify_card_ticket(
                body.card_ticket, request.app.state.settings.admission_diagnostics_secret
            )
            return {"id": card_user_id(card_id)}
        payload = validate_init_data(body.init_data, request.app.state.settings.bot_token)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="invalid_init_data") from exc
    return payload["user"]
