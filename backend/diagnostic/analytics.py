"""Optional, failure-safe analytics adapter with a narrow event contract."""

from __future__ import annotations

import logging
import asyncio
from typing import Any, Final

import aiohttp

from diagnostic.settings import Settings


logger = logging.getLogger(__name__)
ALLOWED_ACTIONS: Final[frozenset[str]] = frozenset(
    {
        "diagnostic_opened",
        "diagnostic_started",
        "diagnostic_completed",
        "diagnostic_result_viewed",
        "diagnostic_pdf_delivered",
        "diagnostic_pdf_failed",
        "diagnostic_followup_sent",
        "diagnostic_followup_failed",
    }
)
ALLOWED_DATA_KEYS: Final[frozenset[str]] = frozenset(
    {
        "attempt_id",
        "diagnostic_id",
        "exam",
        "subject",
        "mode",
        "question_index",
        "question_count",
        "result_status",
        "delivery_status",
    }
)
_INTEGER_DATA_KEYS: Final[frozenset[str]] = frozenset(
    {"question_index", "question_count"}
)


def _safe_data(data: dict[str, Any]) -> dict[str, str | int]:
    safe: dict[str, str | int] = {}
    for key, value in data.items():
        if key not in ALLOWED_DATA_KEYS:
            continue
        if key in _INTEGER_DATA_KEYS:
            if isinstance(value, int) and not isinstance(value, bool):
                safe[key] = value
        elif isinstance(value, str) and len(value) <= 128:
            safe[key] = value
    return safe


async def _post_json(url: str, payload: dict[str, Any], *, timeout: int) -> None:
    client_timeout = aiohttp.ClientTimeout(total=timeout)
    async with aiohttp.ClientSession(timeout=client_timeout) as session:
        async with session.post(url, json=payload) as response:
            response.raise_for_status()


async def emit_event(action: str, user_id: int, data: dict[str, Any]) -> None:
    """Emit only explicitly allowed fields; analytics can never block product flow."""
    if action not in ALLOWED_ACTIONS:
        return
    try:
        settings = Settings.from_env(require_admin=False)
        if not settings.analytics_webhook_url:
            return
        del user_id
        payload = {"action": action, "data": _safe_data(data)}
        await _post_json(settings.analytics_webhook_url, payload, timeout=5)
    except Exception as exc:
        logger.warning("diagnostic_analytics_failed action=%s error=%s", action, type(exc).__name__)


def fire_event(action: str, user_id: int, data: dict[str, Any]) -> None:
    """Schedule failure-safe analytics without delaying product work."""
    task = asyncio.create_task(emit_event(action, user_id, data))
    task.add_done_callback(lambda completed: completed.exception() if not completed.cancelled() else None)
