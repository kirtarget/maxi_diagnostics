"""Operator alerts for conditions nobody would otherwise notice.

Alerting is optional. Without ``ALERT_CHAT_ID`` nothing is configured and every
call is a no-op. Messages carry a kind, counts and identifiers already visible in
the protected admin lists. They never carry ``initData``, Telegram profile data,
answers, payloads or a stack trace with values.

Dedupe is a per-process in-memory map: at most one message per kind per hour in
the process that sends it. The bot is the single worker owner, so in the intended
deployment that is one message per kind per hour overall. A second worker process
would send its own copy.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Final


logger = logging.getLogger(__name__)
DEDUPE_WINDOW_SECONDS: Final[int] = 3600
SEND_TIMEOUT_SECONDS: Final[int] = 10
MAX_TEXT_LENGTH: Final[int] = 512

_bot = None
_chat_id: int | None = None
_last_sent: dict[str, float] = {}


def configure(bot, chat_id: int | None) -> None:
    """Bind alerting to the running bot. A missing chat id disables it."""
    global _bot, _chat_id
    _bot = bot if chat_id is not None else None
    _chat_id = chat_id
    _last_sent.clear()


def reset() -> None:
    configure(None, None)


async def notify(kind: str, text: str) -> None:
    """Send one operator alert. Never raises and never blocks the caller's work."""
    bot, chat_id = _bot, _chat_id
    if bot is None or chat_id is None:
        return
    now = time.monotonic()
    previous = _last_sent.get(kind)
    if previous is not None and now - previous < DEDUPE_WINDOW_SECONDS:
        return
    _last_sent[kind] = now
    message = f"{kind}: {text}"[:MAX_TEXT_LENGTH]
    try:
        await asyncio.wait_for(
            bot.send_message(
                chat_id=chat_id, text=message, disable_web_page_preview=True
            ),
            timeout=SEND_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        logger.warning(
            "diagnostic_alert_failed kind=%s error=%s", kind, type(exc).__name__
        )
