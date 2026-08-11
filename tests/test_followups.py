from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from diagnostic.school import load_school


ROOT = Path(__file__).resolve().parents[1]


def claimed(kind: str = "result_unviewed"):
    return {"id": 9, "user_id": 42, "attempt_id": "attempt_123", "kind": kind, "locked_at": datetime(2026, 8, 11, tzinfo=timezone.utc)}


@pytest.mark.asyncio
async def test_followup_rechecks_viewed_state_under_exact_lease_and_cancels(monkeypatch):
    from diagnostic import followups

    lease = claimed()
    monkeypatch.setattr(followups.attempts, "claim_due_notifications", AsyncMock(return_value=[lease]))
    monkeypatch.setattr(followups.attempts, "get_claimed_notification", AsyncMock(return_value=lease | {"attempt_status": "completed", "result_viewed_at": lease["locked_at"], "subject": "Математика", "mode": "quick"}))
    cancel = AsyncMock(return_value=True)
    monkeypatch.setattr(followups.attempts, "cancel_notification", cancel)
    bot = SimpleNamespace(send_message=AsyncMock())

    assert await followups.dispatch_followups(bot, SimpleNamespace(miniapp_url="https://app.example"), load_school(ROOT / "school")) == 0
    cancel.assert_awaited_once_with(9, lease["locked_at"])
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_followup_sends_known_kind_and_finalizes_exact_lease(monkeypatch):
    from diagnostic import followups

    lease = claimed("quick_to_full")
    context = lease | {"attempt_status": "completed", "result_viewed_at": None, "subject": '<b>Математика</b>', "mode": "quick", "payload": {}}
    monkeypatch.setattr(followups.attempts, "claim_due_notifications", AsyncMock(return_value=[lease]))
    monkeypatch.setattr(followups.attempts, "get_claimed_notification", AsyncMock(return_value=context))
    monkeypatch.setattr(followups, "render_message", AsyncMock(return_value="safe"))
    sent = AsyncMock(return_value=True)
    monkeypatch.setattr(followups.attempts, "mark_notification_sent", sent)
    bot = SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=3)))

    assert await followups.dispatch_followups(bot, SimpleNamespace(miniapp_url="https://app.example"), load_school(ROOT / "school")) == 1
    bot.send_message.assert_awaited_once()
    sent.assert_awaited_once_with(9, lease["locked_at"])


@pytest.mark.asyncio
async def test_followup_deletes_sent_message_when_erasure_wins_finalization(monkeypatch):
    from diagnostic import followups

    lease = claimed("quick_to_full")
    context = lease | {"attempt_status": "completed", "result_viewed_at": None, "subject": "Математика", "mode": "quick", "payload": {}}
    monkeypatch.setattr(followups.attempts, "claim_due_notifications", AsyncMock(return_value=[lease]))
    monkeypatch.setattr(followups.attempts, "get_claimed_notification", AsyncMock(return_value=context))
    monkeypatch.setattr(followups, "render_message", AsyncMock(return_value="safe"))
    monkeypatch.setattr(followups.attempts, "mark_notification_sent", AsyncMock(return_value=False))
    bot = SimpleNamespace(
        send_message=AsyncMock(return_value=SimpleNamespace(message_id=3)),
        delete_message=AsyncMock(),
    )

    assert await followups.dispatch_followups(bot, SimpleNamespace(miniapp_url="https://app.example"), load_school(ROOT / "school")) == 0
    bot.delete_message.assert_awaited_once_with(chat_id=42, message_id=3)


@pytest.mark.asyncio
async def test_followup_deletes_accepted_message_when_database_finalizer_raises(monkeypatch):
    from diagnostic import followups

    lease = claimed("quick_to_full")
    context = lease | {
        "attempt_status": "completed", "result_viewed_at": None,
        "subject": "Математика", "mode": "quick", "payload": {},
    }
    monkeypatch.setattr(followups.attempts, "claim_due_notifications", AsyncMock(return_value=[lease]))
    monkeypatch.setattr(followups.attempts, "get_claimed_notification", AsyncMock(return_value=context))
    monkeypatch.setattr(followups, "render_message", AsyncMock(return_value="safe"))
    monkeypatch.setattr(
        followups.attempts, "mark_notification_sent",
        AsyncMock(side_effect=RuntimeError("db")),
    )
    monkeypatch.setattr(
        followups.attempts, "notification_is_sent", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(
        followups.attempts, "mark_notification_failed", AsyncMock(return_value=False),
    )
    bot = SimpleNamespace(
        send_message=AsyncMock(return_value=SimpleNamespace(message_id=3)),
        delete_message=AsyncMock(),
    )

    assert await followups.dispatch_followups(
        bot, SimpleNamespace(miniapp_url="https://app.example"), load_school(ROOT / "school")
    ) == 0
    bot.delete_message.assert_awaited_once_with(chat_id=42, message_id=3)


@pytest.mark.asyncio
async def test_followup_keeps_message_when_finalizer_committed_before_connection_error(monkeypatch):
    from diagnostic import followups

    lease = claimed("quick_to_full")
    context = lease | {
        "attempt_status": "completed", "result_viewed_at": None,
        "subject": "Математика", "mode": "quick", "payload": {},
    }
    monkeypatch.setattr(followups.attempts, "claim_due_notifications", AsyncMock(return_value=[lease]))
    monkeypatch.setattr(followups.attempts, "get_claimed_notification", AsyncMock(return_value=context))
    monkeypatch.setattr(followups, "render_message", AsyncMock(return_value="safe"))
    monkeypatch.setattr(
        followups.attempts, "mark_notification_sent",
        AsyncMock(side_effect=RuntimeError("lost response")),
    )
    monkeypatch.setattr(
        followups.attempts, "notification_is_sent", AsyncMock(return_value=True)
    )
    bot = SimpleNamespace(
        send_message=AsyncMock(return_value=SimpleNamespace(message_id=3)),
        delete_message=AsyncMock(),
    )

    assert await followups.dispatch_followups(
        bot, SimpleNamespace(miniapp_url="https://app.example"), load_school(ROOT / "school")
    ) == 1
    bot.delete_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_followup_reconciles_commit_error_when_cancelled_during_finalization(monkeypatch):
    from diagnostic import followups

    lease = claimed("quick_to_full")
    context = lease | {
        "attempt_status": "completed", "result_viewed_at": None,
        "subject": "Математика", "mode": "quick", "payload": {},
    }
    finalizer_started = asyncio.Event()
    release_finalizer = asyncio.Event()

    async def commit_then_raise(*_):
        finalizer_started.set()
        await release_finalizer.wait()
        raise RuntimeError("lost response after commit")

    monkeypatch.setattr(followups.attempts, "claim_due_notifications", AsyncMock(return_value=[lease]))
    monkeypatch.setattr(followups.attempts, "get_claimed_notification", AsyncMock(return_value=context))
    monkeypatch.setattr(followups, "render_message", AsyncMock(return_value="safe"))
    monkeypatch.setattr(followups.attempts, "mark_notification_sent", commit_then_raise)
    sent_state = AsyncMock(return_value=True)
    monkeypatch.setattr(followups.attempts, "notification_is_sent", sent_state)
    failed = AsyncMock(return_value=False)
    monkeypatch.setattr(followups.attempts, "mark_notification_failed", failed)
    bot = SimpleNamespace(
        send_message=AsyncMock(return_value=SimpleNamespace(message_id=3)),
        delete_message=AsyncMock(),
    )

    task = asyncio.create_task(followups.dispatch_followups(
        bot, SimpleNamespace(miniapp_url="https://app.example"), load_school(ROOT / "school")
    ))
    await finalizer_started.wait()
    task.cancel()
    release_finalizer.set()

    with pytest.raises(asyncio.CancelledError):
        await task
    sent_state.assert_awaited_once_with(9)
    failed.assert_not_awaited()
    bot.delete_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_followup_deletes_known_message_after_failure_finalizer_resolves_uncertainty(monkeypatch):
    from diagnostic import followups

    lease = claimed("quick_to_full")
    context = lease | {
        "attempt_status": "completed", "result_viewed_at": None,
        "subject": "Математика", "mode": "quick", "payload": {},
    }
    monkeypatch.setattr(followups.attempts, "claim_due_notifications", AsyncMock(return_value=[lease]))
    monkeypatch.setattr(followups.attempts, "get_claimed_notification", AsyncMock(return_value=context))
    monkeypatch.setattr(followups, "render_message", AsyncMock(return_value="safe"))
    monkeypatch.setattr(
        followups.attempts, "mark_notification_sent", AsyncMock(side_effect=RuntimeError("db")),
    )
    monkeypatch.setattr(
        followups.attempts, "notification_is_sent", AsyncMock(side_effect=RuntimeError("db")),
    )
    monkeypatch.setattr(
        followups.attempts, "mark_notification_failed", AsyncMock(return_value=True),
    )
    bot = SimpleNamespace(
        send_message=AsyncMock(return_value=SimpleNamespace(message_id=3)),
        delete_message=AsyncMock(),
    )

    assert await followups.dispatch_followups(
        bot, SimpleNamespace(miniapp_url="https://app.example"), load_school(ROOT / "school")
    ) == 0
    bot.delete_message.assert_awaited_once_with(chat_id=42, message_id=3)


@pytest.mark.asyncio
async def test_followup_unknown_kind_is_cancelled_without_sending(monkeypatch):
    from diagnostic import followups

    lease = claimed("legacy_funnel")
    monkeypatch.setattr(followups.attempts, "claim_due_notifications", AsyncMock(return_value=[lease]))
    monkeypatch.setattr(followups.attempts, "get_claimed_notification", AsyncMock(return_value=lease))
    cancel = AsyncMock(return_value=True)
    monkeypatch.setattr(followups.attempts, "cancel_notification", cancel)
    bot = SimpleNamespace(send_message=AsyncMock())

    assert await followups.dispatch_followups(bot, SimpleNamespace(miniapp_url="https://app.example"), load_school(ROOT / "school")) == 0
    cancel.assert_awaited_once_with(9, lease["locked_at"])
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_incomplete_followup_is_cancelled_after_attempt_completes(monkeypatch):
    from diagnostic import followups

    lease = claimed("incomplete")
    monkeypatch.setattr(followups.attempts, "claim_due_notifications", AsyncMock(return_value=[lease]))
    monkeypatch.setattr(followups.attempts, "get_claimed_notification", AsyncMock(return_value=lease | {"attempt_status": "completed"}))
    cancel = AsyncMock(return_value=True)
    monkeypatch.setattr(followups.attempts, "cancel_notification", cancel)
    bot = SimpleNamespace(send_message=AsyncMock())

    assert await followups.dispatch_followups(bot, SimpleNamespace(miniapp_url="https://app.example"), load_school(ROOT / "school")) == 0
    cancel.assert_awaited_once_with(9, lease["locked_at"])


@pytest.mark.asyncio
async def test_followup_does_nothing_after_claim_was_cancelled_or_reclaimed(monkeypatch):
    from diagnostic import followups

    lease = claimed("result_unviewed")
    monkeypatch.setattr(followups.attempts, "claim_due_notifications", AsyncMock(return_value=[lease]))
    monkeypatch.setattr(followups.attempts, "get_claimed_notification", AsyncMock(return_value=None))
    cancel = AsyncMock()
    monkeypatch.setattr(followups.attempts, "cancel_notification", cancel)
    bot = SimpleNamespace(send_message=AsyncMock())

    assert await followups.dispatch_followups(bot, SimpleNamespace(miniapp_url="https://app.example"), load_school(ROOT / "school")) == 0
    cancel.assert_not_awaited()
    bot.send_message.assert_not_awaited()
