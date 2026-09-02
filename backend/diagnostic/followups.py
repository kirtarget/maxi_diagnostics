"""Reliable diagnostic-only follow-up delivery."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from typing import Any, Final

from aiogram import Bot

from diagnostic.analytics import fire_event
from diagnostic.bot.keyboards import home_keyboard, result_keyboard, webapp_keyboard
from diagnostic.db import attempts
from diagnostic.delivery_state import reconcile_sent_finalizer
from diagnostic.messages import render_message
from diagnostic.school import SchoolConfig
from diagnostic.settings import Settings


logger = logging.getLogger(__name__)
_MESSAGE_KEYS: Final[dict[str, str]] = {
    "not_started": "NOT_STARTED",
    "incomplete": "INCOMPLETE",
    "result_unviewed": "RESULT_UNVIEWED",
    "day_followup": "DAY_FOLLOWUP",
    "quick_to_full": "QUICK_TO_FULL",
    "month_retest": "MONTH_RETEST",
    "lives_refill": "LIVES_REFILL",
}


def _value(row: Mapping[str, Any], key: str, default: Any = None) -> Any:
    try:
        value = row[key]
    except (KeyError, TypeError):
        value = default
    return default if value is None else value


def _eligible(row: Mapping[str, Any]) -> bool:
    kind = str(_value(row, "kind", ""))
    status = _value(row, "attempt_status")
    if kind == "not_started":
        return _value(row, "attempt_id") is None
    if kind == "lives_refill":
        return True
    if kind == "incomplete":
        return status == "in_progress"
    if status != "completed":
        return False
    if kind == "result_unviewed":
        return _value(row, "result_viewed_at") is None
    if kind == "quick_to_full":
        return _value(row, "mode") == "quick" and not _value(row, "has_later_full", False)
    return kind in _MESSAGE_KEYS


def _keyboard(row: Mapping[str, Any], settings: Settings, school: SchoolConfig):
    kind = str(_value(row, "kind", ""))
    user_id = int(_value(row, "user_id"))
    if kind in {"not_started", "incomplete", "quick_to_full", "month_retest", "lives_refill"}:
        label = (
            school.brand.interface.take_full_diagnostic
            if kind == "quick_to_full"
            else school.brand.interface.start_diagnostic
        )
        return webapp_keyboard(school, settings.miniapp_url, label=label)
    attempt_id = _value(row, "attempt_id")
    if attempt_id:
        return result_keyboard(
            school,
            user_id,
            str(attempt_id),
            str(_value(row, "mode", "full")),
            miniapp_url=settings.miniapp_url,
        )
    return home_keyboard(school, settings.miniapp_url, user_id)


async def dispatch_followups(
    bot: Bot, settings: Settings, school: SchoolConfig, *, limit: int = 20
) -> int:
    """Send at most ``limit`` claimed notifications after an exact-lease recheck."""
    sent_count = 0
    processed: set[int] = set()
    for _ in range(max(1, min(limit, 20))):
        claims = await attempts.claim_due_notifications(limit=1)
        if not claims:
            break
        claim = claims[0]
        notification_id = claim["id"]
        if notification_id in processed:
            break
        processed.add(notification_id)
        lease = claim["locked_at"]
        row = await attempts.get_claimed_notification(notification_id, lease)
        if row is None:
            continue
        kind = str(_value(row, "kind", ""))
        if kind not in _MESSAGE_KEYS or not _eligible(row):
            await attempts.cancel_notification(notification_id, lease)
            continue
        message_id: int | None = None
        finalized = False
        finalizer_uncertain = False
        try:
            text = await render_message(
                _MESSAGE_KEYS[kind],
                school,
                subject=_value(row, "subject", "diagnostic"),
                mode=_value(row, "mode", "full"),
            )
            message = await asyncio.wait_for(
                bot.send_message(
                    chat_id=row["user_id"],
                    text=text,
                    parse_mode="HTML",
                    reply_markup=_keyboard(row, settings, school),
                    disable_web_page_preview=True,
                ),
                timeout=30,
            )
            message_id = getattr(message, "message_id", None)
            if not isinstance(message_id, int) or isinstance(message_id, bool) or message_id <= 0:
                raise RuntimeError("telegram_message_id_missing")
            finalizer_uncertain = True
            finalizer = asyncio.create_task(
                attempts.mark_notification_sent(notification_id, lease)
            )
            finalizer_result = await reconcile_sent_finalizer(
                finalizer,
                lambda: attempts.notification_is_sent(notification_id),
            )
            finalized = finalizer_result.sent
            finalizer_uncertain = finalizer_result.uncertain
            if finalizer_result.cancelled:
                raise asyncio.CancelledError
            if finalizer_result.error is not None:
                if finalized:
                    sent_count += 1
                    fire_event(
                        "diagnostic_followup_sent", row["user_id"],
                        {"attempt_id": str(_value(row, "attempt_id", "")), "delivery_status": "sent"},
                    )
                    continue
                raise finalizer_result.error
            if finalized:
                sent_count += 1
                fire_event(
                    "diagnostic_followup_sent", row["user_id"],
                    {"attempt_id": str(_value(row, "attempt_id", "")), "delivery_status": "sent"},
                )
            else:
                try:
                    await asyncio.wait_for(
                        bot.delete_message(chat_id=row["user_id"], message_id=message_id),
                        timeout=10,
                    )
                except Exception:
                    logger.warning("diagnostic_followup_cleanup_failed error=telegram_delete_failed")
        except BaseException as exc:
            if finalized and isinstance(exc, asyncio.CancelledError):
                raise
            if message_id is not None and not finalized and not finalizer_uncertain:
                try:
                    await asyncio.shield(asyncio.wait_for(
                        bot.delete_message(chat_id=row["user_id"], message_id=message_id),
                        timeout=10,
                    ))
                except BaseException:
                    logger.warning("diagnostic_followup_cleanup_failed error=telegram_delete_failed")
            error_status = type(exc).__name__
            logger.warning("diagnostic_followup_failed kind=%s error=%s", kind, error_status)
            try:
                failed = await asyncio.shield(
                    attempts.mark_notification_failed(notification_id, lease, error_status)
                )
            except BaseException:
                logger.warning("diagnostic_followup_failure_finalize_failed error=database_error")
                failed = False
            if failed:
                if message_id is not None and not finalized and finalizer_uncertain:
                    try:
                        await asyncio.shield(asyncio.wait_for(
                            bot.delete_message(chat_id=row["user_id"], message_id=message_id),
                            timeout=10,
                        ))
                    except BaseException:
                        logger.warning("diagnostic_followup_cleanup_failed error=telegram_delete_failed")
                fire_event(
                    "diagnostic_followup_failed", row["user_id"],
                    {"attempt_id": str(_value(row, "attempt_id", "")), "delivery_status": "failed"},
                )
            if isinstance(exc, asyncio.CancelledError):
                raise
    return sent_count
