"""Reliable result delivery using the persisted exact-lease state machine."""

from __future__ import annotations

import asyncio
import html
import logging
from typing import Any, Literal

from aiogram import Bot

from diagnostic import alerts
from diagnostic.analytics import fire_event
from diagnostic.bot.keyboards import attempt_result_url, webapp_keyboard
from diagnostic.db import attempts
from diagnostic.delivery_state import reconcile_sent_finalizer
from diagnostic.messages import render_message
from diagnostic.school import SchoolConfig, load_school
from diagnostic.settings import Settings


logger = logging.getLogger(__name__)
DeliveryOutcome = Literal["empty", "sent", "failed"]
MESSAGE_LIMIT = 4096


async def _delete_sent_message(bot: Bot, user_id: int, message_id: int) -> None:
    try:
        await asyncio.wait_for(
            bot.delete_message(chat_id=user_id, message_id=message_id), timeout=10
        )
    except BaseException:
        logger.warning("diagnostic_result_cleanup_failed error=telegram_delete_failed")


async def _alert_if_abandoned(attempt_id: str, error_status: str) -> None:
    """Alerting must never turn a handled delivery failure into an exception."""
    try:
        if await attempts.delivery_is_abandoned(attempt_id):
            await alerts.notify(
                "delivery_abandoned",
                f"attempt={attempt_id} attempts=8 error={error_status}",
            )
    except Exception:
        logger.warning("diagnostic_result_alert_failed error=database_error")


def _result_summary(row: Any, school: SchoolConfig) -> str:
    """One escaped score line, so the chat says what the Mini App will show."""
    labels = school.brand.interface
    subject = str(row["subject"] or labels.diagnostic_fallback)
    correct = int(row["correct_count"] or 0)
    total = int(row["question_count"] or 0)
    return (
        f"<b>{html.escape(subject, quote=True)}</b>\n"
        f"{html.escape(labels.result_correct, quote=True)}: {correct} из {total}"
    )


async def deliver_attempt(
    bot: Bot,
    attempt_id: str | None = None,
    *,
    settings: Settings,
    school: SchoolConfig | None = None,
) -> DeliveryOutcome:
    """Claim one completed attempt, deliver it, and finalize its exact lease."""
    row = await attempts.claim_pending_delivery(attempt_id)
    if row is None:
        return "empty"
    lease = row["pdf_locked_at"]
    message_id: int | None = None
    finalized = False
    finalizer_uncertain = False
    try:
        actual_school = school if school is not None else load_school()
        key = "QUICK_COMPLETE" if row["mode"] == "quick" else "FULL_COMPLETE"
        intro = await render_message(key, actual_school, subject=row["subject"])
        text = f"{intro}\n\n{_result_summary(row, actual_school)}"
        if len(text) > MESSAGE_LIMIT:
            text = _result_summary(row, actual_school)
        keyboard = webapp_keyboard(
            actual_school,
            attempt_result_url(settings.miniapp_url, row["attempt_id"]),
            label=actual_school.brand.interface.result_in_app,
        )
        if not await attempts.delivery_claim_is_active(row["attempt_id"], lease):
            return "failed"
        message = await asyncio.wait_for(
            bot.send_message(
                chat_id=row["user_id"],
                text=text,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=keyboard,
            ),
            timeout=30,
        )
        message_id = getattr(message, "message_id", None)
        if not isinstance(message_id, int) or isinstance(message_id, bool) or message_id <= 0:
            raise RuntimeError("telegram_message_id_missing")
        finalizer_uncertain = True
        finalizer = asyncio.create_task(
            attempts.mark_delivery_sent(row["attempt_id"], lease, message_id)
        )
        finalizer_result = await reconcile_sent_finalizer(
            finalizer,
            lambda: attempts.delivery_is_sent(row["attempt_id"], message_id),
        )
        finalized = finalizer_result.sent
        finalizer_uncertain = finalizer_result.uncertain
        if finalizer_result.cancelled:
            raise asyncio.CancelledError
        if finalizer_result.error is not None:
            if finalized:
                fire_event(
                    "diagnostic_result_delivered", row["user_id"],
                    {"attempt_id": row["attempt_id"], "delivery_status": "sent"},
                )
                return "sent"
            raise finalizer_result.error
        if finalized:
            fire_event(
                "diagnostic_result_delivered", row["user_id"],
                {"attempt_id": row["attempt_id"], "delivery_status": "sent"},
            )
            return "sent"
        await _delete_sent_message(bot, row["user_id"], message_id)
        return "failed"
    except BaseException as exc:
        if finalized and isinstance(exc, asyncio.CancelledError):
            raise
        if message_id is not None and not finalized and not finalizer_uncertain:
            await asyncio.shield(_delete_sent_message(bot, row["user_id"], message_id))
        error_status = type(exc).__name__
        logger.warning("diagnostic_result_delivery_failed error=%s", error_status)
        try:
            failed = await asyncio.shield(
                attempts.mark_delivery_failed(row["attempt_id"], lease, error_status)
            )
        except BaseException:
            logger.warning("diagnostic_result_failure_finalize_failed error=database_error")
            failed = False
        if failed:
            if message_id is not None and not finalized and finalizer_uncertain:
                await asyncio.shield(_delete_sent_message(bot, row["user_id"], message_id))
            fire_event(
                "diagnostic_result_delivery_failed", row["user_id"],
                {"attempt_id": row["attempt_id"], "delivery_status": "failed"},
            )
            # A cancelled task must not await anything else before re-raising.
            if not isinstance(exc, asyncio.CancelledError):
                await asyncio.shield(
                    _alert_if_abandoned(row["attempt_id"], error_status)
                )
        if isinstance(exc, asyncio.CancelledError):
            raise
        return "failed"


async def deliver_attempt_by_id(attempt_id: str) -> None:
    """BackgroundTasks-safe delivery with a short-lived, always-closed Bot."""
    settings = Settings.from_env(require_admin=False)
    bot = Bot(token=settings.bot_token)
    try:
        await deliver_attempt(bot, attempt_id, settings=settings)
    finally:
        await bot.session.close()
