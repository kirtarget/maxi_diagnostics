"""Telegram Mini App initData validation without network access."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
from typing import Any
from urllib.parse import parse_qsl


_HASH_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_MAX_TELEGRAM_USER_ID = 2**63 - 1
_MAX_FUTURE_SKEW_SECONDS = 30


def validate_init_data(
    init_data: str, bot_token: str, max_age_seconds: int = 7200
) -> dict[str, Any]:
    """Verify Telegram's signed WebApp initData and return its parsed payload."""
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise ValueError("initData missing hash")
    if not _HASH_PATTERN.fullmatch(received_hash):
        raise ValueError("initData hash is invalid")
    check_string = "\n".join(f"{key}={pairs[key]}" for key in sorted(pairs))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated_hash, received_hash):
        raise ValueError("initData hash mismatch")
    try:
        auth_date = int(pairs.get("auth_date", "0"))
    except ValueError as exc:
        raise ValueError("initData auth_date is invalid") from exc
    now = time.time()
    if now - auth_date > max_age_seconds:
        raise ValueError("initData auth_date is stale")
    if auth_date - now > _MAX_FUTURE_SKEW_SECONDS:
        raise ValueError("initData auth_date is from the future")
    try:
        user = json.loads(pairs["user"])
    except KeyError as exc:
        raise ValueError("initData missing user") from exc
    except json.JSONDecodeError as exc:
        raise ValueError("initData user is not valid JSON") from exc
    user_id = user.get("id") if isinstance(user, dict) else None
    if (
        isinstance(user_id, bool)
        or not isinstance(user_id, int)
        or not 0 < user_id <= _MAX_TELEGRAM_USER_ID
    ):
        raise ValueError("initData user is invalid")
    pairs["user"] = user
    return pairs
