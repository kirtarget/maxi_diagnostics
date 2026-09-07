"""Bounded in-process delivery worker and scheduler configuration."""

from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from diagnostic import alerts
from diagnostic.delivery import deliver_attempt
from diagnostic.db import attempts, funnel
from diagnostic.followups import dispatch_followups
from diagnostic.school import SchoolConfig
from diagnostic.settings import Settings


DELIVERY_BATCH_LIMIT = 20
NOTIFICATION_BATCH_LIMIT = 20
PENDING_DELIVERY_ALERT_THRESHOLD = 50
STREAK_SAVE_HOUR = 20


async def dispatch_work(
    bot,
    settings: Settings,
    school: SchoolConfig,
) -> dict[str, int]:
    try:
        return await _dispatch_work(bot, settings, school)
    except Exception as exc:
        await alerts.notify(
            "worker_tick_failed", f"error={type(exc).__name__}: {exc}"
        )
        raise


async def _dispatch_work(
    bot,
    settings: Settings,
    school: SchoolConfig,
) -> dict[str, int]:
    pending = await attempts.count_pending_deliveries()
    if pending > PENDING_DELIVERY_ALERT_THRESHOLD:
        await alerts.notify(
            "delivery_queue_backlog",
            f"pending={pending} threshold={PENDING_DELIVERY_ALERT_THRESHOLD}",
        )
    await attempts.purge_expired_erasure_tombstones()
    await funnel.record_abandoned_attempts(settings.application_secret)
    await attempts.purge_retained_diagnostic_data(
        settings.application_secret,
        settings.diagnostic_retention_days,
        settings.in_progress_retention_days,
    )
    deliveries = 0
    for _ in range(DELIVERY_BATCH_LIMIT):
        outcome = await deliver_attempt(bot, settings=settings, school=school)
        if outcome == "empty":
            break
        if outcome == "sent":
            deliveries += 1
    await attempts.schedule_streak_save_notifications(
        timezone_name=settings.timezone, send_hour=STREAK_SAVE_HOUR
    )
    notifications = await dispatch_followups(
        bot, settings, school, limit=NOTIFICATION_BATCH_LIMIT
    )
    return {"deliveries": deliveries, "notifications": notifications}


def build_worker_scheduler(
    bot,
    settings: Settings,
    school: SchoolConfig,
) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=settings.timezone)
    scheduler.add_job(
        dispatch_work,
        "interval",
        minutes=1,
        id="diagnostic_delivery",
        args=(bot, settings, school),
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,
        replace_existing=True,
    )
    return scheduler
