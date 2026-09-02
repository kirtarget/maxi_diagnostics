"""Bounded in-process delivery worker and scheduler configuration."""

from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from diagnostic import alerts
from diagnostic.catalog import DiagnosticCatalog
from diagnostic.delivery import deliver_attempt
from diagnostic.db import attempts
from diagnostic.followups import dispatch_followups
from diagnostic.school import SchoolConfig
from diagnostic.settings import Settings


PDF_BATCH_LIMIT = 20
NOTIFICATION_BATCH_LIMIT = 20
PENDING_PDF_ALERT_THRESHOLD = 50


async def dispatch_work(
    bot,
    settings: Settings,
    school: SchoolConfig,
    catalog: DiagnosticCatalog | None = None,
) -> dict[str, int]:
    try:
        return await _dispatch_work(bot, settings, school, catalog)
    except Exception as exc:
        await alerts.notify(
            "worker_tick_failed", f"error={type(exc).__name__}: {exc}"
        )
        raise


async def _dispatch_work(
    bot,
    settings: Settings,
    school: SchoolConfig,
    catalog: DiagnosticCatalog | None,
) -> dict[str, int]:
    pending = await attempts.count_pending_pdfs()
    if pending > PENDING_PDF_ALERT_THRESHOLD:
        await alerts.notify(
            "pdf_queue_backlog",
            f"pending={pending} threshold={PENDING_PDF_ALERT_THRESHOLD}",
        )
    await attempts.purge_expired_erasure_tombstones()
    await attempts.purge_retained_diagnostic_data(
        settings.application_secret,
        settings.diagnostic_retention_days,
        settings.in_progress_retention_days,
    )
    pdfs = 0
    for _ in range(PDF_BATCH_LIMIT):
        outcome = await deliver_attempt(bot, school=school, catalog=catalog)
        if outcome == "empty":
            break
        if outcome == "sent":
            pdfs += 1
    notifications = await dispatch_followups(
        bot, settings, school, limit=NOTIFICATION_BATCH_LIMIT
    )
    return {"pdfs": pdfs, "notifications": notifications}


def build_worker_scheduler(
    bot,
    settings: Settings,
    school: SchoolConfig,
    catalog: DiagnosticCatalog,
) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=settings.timezone)
    scheduler.add_job(
        dispatch_work,
        "interval",
        minutes=1,
        id="diagnostic_delivery",
        args=(bot, settings, school, catalog),
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,
        replace_existing=True,
    )
    return scheduler
