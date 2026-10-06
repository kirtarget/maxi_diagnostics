"""Diagnostics-only admission card credentials."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import time

CARD_ID_PATTERN = r"^[a-f0-9-]{36}$"


def card_user_id(card_id: str) -> int:
    digest = hashlib.sha256(b"admission-card:" + card_id.encode()).digest()
    return -((int.from_bytes(digest[:8], "big") >> 2) + 1)


def verify_card_ticket(ticket: str, secret: str, *, now: float | None = None) -> str:
    try:
        if not secret or len(ticket) > 512:
            raise ValueError("invalid_card_ticket")
        version, payload, signature = ticket.split(".")
        if version != "v1" or not re.fullmatch(r"[A-Za-z0-9_-]+", payload):
            raise ValueError("invalid_card_ticket")
        expected = base64.urlsafe_b64encode(
            hmac.digest(secret.encode(), f"v1.{payload}".encode(), "sha256")
        ).decode().rstrip("=")
        if not hmac.compare_digest(expected, signature):
            raise ValueError("invalid_card_ticket")
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        if (
            not isinstance(data, dict)
            or set(data) != {"c", "e"}
            or not isinstance(data["c"], str)
            or not re.fullmatch(CARD_ID_PATTERN, data["c"])
            or type(data["e"]) is not int
            or data["e"] <= (time.time() if now is None else now)
        ):
            raise ValueError("invalid_card_ticket")
        return data["c"]
    except (ValueError, TypeError, UnicodeError) as exc:
        raise ValueError("invalid_card_ticket") from exc
