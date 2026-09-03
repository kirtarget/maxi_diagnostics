from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock

import pytest


@pytest.mark.asyncio
async def test_dispatch_work_caps_pdf_and_notification_batches(monkeypatch):
    from diagnostic import worker

    deliver = AsyncMock(return_value="sent")
    followups = AsyncMock(return_value=20)
    monkeypatch.setattr(worker, "deliver_attempt", deliver)
    monkeypatch.setattr(worker, "dispatch_followups", followups)
    purge = AsyncMock(return_value=1)
    monkeypatch.setattr(worker.attempts, "purge_expired_erasure_tombstones", purge)
    retention = AsyncMock(return_value={})
    monkeypatch.setattr(worker.attempts, "purge_retained_diagnostic_data", retention)
    monkeypatch.setattr(worker.attempts, "count_pending_pdfs", AsyncMock(return_value=0))
    monkeypatch.setattr(
        worker.attempts, "schedule_streak_save_notifications", AsyncMock(return_value=0)
    )

    settings = SimpleNamespace(
        application_secret="stable-secret", diagnostic_retention_days=365,
        in_progress_retention_days=30, timezone="Europe/Moscow",
    )
    counts = await worker.dispatch_work(SimpleNamespace(), settings, SimpleNamespace())

    assert counts == {"pdfs": 20, "notifications": 20}
    assert deliver.await_count == 20
    followups.assert_awaited_once_with(ANY, ANY, ANY, limit=20)
    purge.assert_awaited_once_with()
    retention.assert_awaited_once_with("stable-secret", 365, 30)


@pytest.mark.asyncio
async def test_dispatch_work_continues_after_poison_pdf_and_stops_only_when_empty(monkeypatch):
    from diagnostic import worker

    deliver = AsyncMock(side_effect=["failed", "sent", "empty"])
    monkeypatch.setattr(worker, "deliver_attempt", deliver)
    monkeypatch.setattr(worker, "dispatch_followups", AsyncMock(return_value=0))
    monkeypatch.setattr(
        worker.attempts, "purge_expired_erasure_tombstones", AsyncMock(return_value=0)
    )
    monkeypatch.setattr(
        worker.attempts, "purge_retained_diagnostic_data", AsyncMock(return_value={})
    )
    monkeypatch.setattr(worker.attempts, "count_pending_pdfs", AsyncMock(return_value=0))
    monkeypatch.setattr(
        worker.attempts, "schedule_streak_save_notifications", AsyncMock(return_value=0)
    )

    settings = SimpleNamespace(
        application_secret="stable-secret", diagnostic_retention_days=365,
        in_progress_retention_days=30, timezone="Europe/Moscow",
    )
    counts = await worker.dispatch_work(SimpleNamespace(), settings, SimpleNamespace())

    assert deliver.await_count == 3
    assert counts == {"pdfs": 1, "notifications": 0}


@pytest.mark.asyncio
async def test_backlog_and_tick_failure_reach_the_operator_alert(monkeypatch):
    from diagnostic import worker

    alerted = []

    async def notify(kind, text):
        alerted.append((kind, text))

    monkeypatch.setattr(worker.alerts, "notify", notify)
    monkeypatch.setattr(
        worker.attempts, "count_pending_pdfs", AsyncMock(return_value=51)
    )
    monkeypatch.setattr(
        worker.attempts,
        "purge_expired_erasure_tombstones",
        AsyncMock(side_effect=RuntimeError("database gone")),
    )
    settings = SimpleNamespace(
        application_secret="stable-secret", diagnostic_retention_days=365,
        in_progress_retention_days=30, timezone="Europe/Moscow",
    )

    with pytest.raises(RuntimeError):
        await worker.dispatch_work(SimpleNamespace(), settings, SimpleNamespace())

    assert alerted == [
        ("pdf_queue_backlog", "pending=51 threshold=50"),
        ("worker_tick_failed", "error=RuntimeError: database gone"),
    ]


@pytest.mark.asyncio
async def test_dispatch_work_schedules_streak_saves_in_school_time(monkeypatch):
    from diagnostic import worker

    monkeypatch.setattr(worker, "deliver_attempt", AsyncMock(return_value="empty"))
    monkeypatch.setattr(worker, "dispatch_followups", AsyncMock(return_value=0))
    monkeypatch.setattr(
        worker.attempts, "purge_expired_erasure_tombstones", AsyncMock(return_value=0)
    )
    monkeypatch.setattr(
        worker.attempts, "purge_retained_diagnostic_data", AsyncMock(return_value={})
    )
    monkeypatch.setattr(worker.attempts, "count_pending_pdfs", AsyncMock(return_value=0))
    schedule = AsyncMock(return_value=3)
    monkeypatch.setattr(worker.attempts, "schedule_streak_save_notifications", schedule)

    settings = SimpleNamespace(
        application_secret="stable-secret", diagnostic_retention_days=365,
        in_progress_retention_days=30, timezone="Europe/Moscow",
    )
    await worker.dispatch_work(SimpleNamespace(), settings, SimpleNamespace())

    schedule.assert_awaited_once_with(timezone_name="Europe/Moscow", send_hour=20)


def test_worker_scheduler_runs_every_minute_with_single_instance():
    from diagnostic.worker import build_worker_scheduler

    scheduler = build_worker_scheduler(SimpleNamespace(), SimpleNamespace(timezone="Europe/Moscow"), SimpleNamespace(), SimpleNamespace())
    job = scheduler.get_job("diagnostic_delivery")

    assert str(job.trigger.interval) == "0:01:00"
    assert job.max_instances == 1
    assert job.coalesce is True
    assert job.misfire_grace_time == 300
