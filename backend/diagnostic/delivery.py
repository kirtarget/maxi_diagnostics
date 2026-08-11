"""Reliable PDF delivery using the persisted exact-lease state machine."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from pathlib import Path
from typing import Literal

from aiogram import Bot
from aiogram.types import BufferedInputFile

from diagnostic.analytics import fire_event
from diagnostic.catalog import DiagnosticCatalog, load_catalog
from diagnostic.db import attempts
from diagnostic.delivery_state import reconcile_sent_finalizer
from diagnostic.messages import render_message
from diagnostic.report import build_report
from diagnostic.school import SchoolConfig, load_school
from diagnostic.settings import Settings


logger = logging.getLogger(__name__)
DeliveryOutcome = Literal["empty", "sent", "failed"]


async def _delete_sent_message(bot: Bot, user_id: int, message_id: int) -> None:
    try:
        await asyncio.wait_for(
            bot.delete_message(chat_id=user_id, message_id=message_id), timeout=10
        )
    except BaseException:
        logger.warning("diagnostic_pdf_cleanup_failed error=telegram_delete_failed")


async def deliver_attempt(
    bot: Bot,
    attempt_id: str | None = None,
    *,
    school: SchoolConfig | None = None,
    catalog: DiagnosticCatalog | None = None,
) -> DeliveryOutcome:
    """Claim one completed attempt, deliver it, and finalize its exact lease."""
    row = await attempts.claim_pending_pdf(attempt_id)
    if row is None:
        return "empty"
    lease = row["pdf_locked_at"]
    message_id: int | None = None
    finalized = False
    finalizer_uncertain = False
    try:
        actual_school = school
        if actual_school is None:
            snapshot = row.get("report_snapshot") or {}
            frozen_school = snapshot.get("school") if isinstance(snapshot, dict) else None
            if isinstance(frozen_school, dict):
                actual_school = SchoolConfig(
                    root=Path("school").resolve(),
                    brand=frozen_school["brand"],
                    links=frozen_school["links"],
                )
            else:
                actual_school = load_school()
        stored_pdf = row.get("pdf_document")
        if stored_pdf:
            pdf = bytes(stored_pdf)
        else:
            bundle_id = row.get("report_asset_bundle_id")
            if bundle_id:
                bundle = row.get("report_assets")
                if not bundle:
                    bundle = await attempts.get_report_asset_bundle(bundle_id)
                if not isinstance(bundle, (bytes, bytearray, memoryview)):
                    raise ValueError("report_assets_invalid")
                bundle = bytes(bundle)
                if hashlib.sha256(bundle).hexdigest() != bundle_id:
                    raise ValueError("report_assets_invalid")
                row = dict(row)
                row["report_assets"] = bundle
            actual_catalog = catalog
            if not row.get("report_snapshot") and actual_catalog is None:
                actual_catalog = load_catalog(actual_school)
            pdf = await asyncio.to_thread(build_report, row, actual_school, actual_catalog)
            if not await attempts.store_pdf_document(row["attempt_id"], lease, pdf):
                return "failed"
        key = "QUICK_COMPLETE" if row["mode"] == "quick" else "FULL_COMPLETE"
        caption = await render_message(key, actual_school, subject=row["subject"])
        document_kwargs = {
            "chat_id": row["user_id"],
            "document": BufferedInputFile(pdf, filename=f"diagnostic-{row['attempt_id']}.pdf"),
            "disable_content_type_detection": True,
        }
        if len(caption) <= 1024:
            document_kwargs.update({"caption": caption, "parse_mode": "HTML"})
        if not await attempts.pdf_claim_is_active(row["attempt_id"], lease):
            return "failed"
        message = await asyncio.wait_for(
            bot.send_document(**document_kwargs), timeout=30
        )
        message_id = getattr(message, "message_id", None)
        if not isinstance(message_id, int) or isinstance(message_id, bool) or message_id <= 0:
            raise RuntimeError("telegram_message_id_missing")
        finalizer_uncertain = True
        finalizer = asyncio.create_task(
            attempts.mark_pdf_delivered(row["attempt_id"], lease, message_id)
        )
        finalizer_result = await reconcile_sent_finalizer(
            finalizer,
            lambda: attempts.pdf_delivery_is_sent(row["attempt_id"], message_id),
        )
        finalized = finalizer_result.sent
        finalizer_uncertain = finalizer_result.uncertain
        if finalizer_result.cancelled:
            raise asyncio.CancelledError
        if finalizer_result.error is not None:
            if finalized:
                fire_event(
                    "diagnostic_pdf_delivered", row["user_id"],
                    {"attempt_id": row["attempt_id"], "delivery_status": "sent"},
                )
                return "sent"
            raise finalizer_result.error
        if finalized:
            fire_event(
                "diagnostic_pdf_delivered", row["user_id"],
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
        logger.warning("diagnostic_pdf_delivery_failed error=%s", error_status)
        try:
            failed = await asyncio.shield(
                attempts.mark_pdf_failed(row["attempt_id"], lease, error_status)
            )
        except BaseException:
            logger.warning("diagnostic_pdf_failure_finalize_failed error=database_error")
            failed = False
        if failed:
            if message_id is not None and not finalized and finalizer_uncertain:
                await asyncio.shield(_delete_sent_message(bot, row["user_id"], message_id))
            fire_event(
                "diagnostic_pdf_failed", row["user_id"],
                {"attempt_id": row["attempt_id"], "delivery_status": "failed"},
            )
        if isinstance(exc, asyncio.CancelledError):
            raise
        return "failed"


async def deliver_attempt_by_id(attempt_id: str) -> None:
    """BackgroundTasks-safe delivery with a short-lived, always-closed Bot."""
    settings = Settings.from_env(require_admin=False)
    bot = Bot(token=settings.bot_token)
    try:
        await deliver_attempt(bot, attempt_id)
    finally:
        await bot.session.close()
