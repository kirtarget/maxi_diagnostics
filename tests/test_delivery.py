from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from diagnostic.school import load_school


ROOT = Path(__file__).resolve().parents[1]


def load_test_school():
    return load_school(ROOT / "tests/fixtures/sample-school")


def delivery_settings():
    return SimpleNamespace(miniapp_url="https://miniapp.example.com/")


@pytest.fixture(autouse=True)
def active_delivery_claim(monkeypatch):
    from diagnostic import delivery

    monkeypatch.setattr(
        delivery.attempts, "delivery_claim_is_active", AsyncMock(return_value=True)
    )


def claimed_attempt():
    return {
        "attempt_id": "attempt_123",
        "user_id": 42,
        "diagnostic_id": "demo-math",
        "subject": "Математика",
        "mode": "quick",
        "status": "completed",
        "question_count": 2,
        "answers": {"q1": "2", "q2": ["1", "3"]},
        "correct_count": 2,
        "score": 100,
        "max_score": 100,
        "score_unit": "accuracy_percent",
        "strong_topics": [],
        "growth_topics": [],
        "result_snapshot": {"score": 100},
        "pdf_locked_at": datetime(2026, 8, 11, tzinfo=timezone.utc),
    }


def sending_bot(message_id: int = 77, **extra):
    return SimpleNamespace(
        send_message=AsyncMock(return_value=SimpleNamespace(message_id=message_id)),
        **extra,
    )


@pytest.mark.asyncio
async def test_delivery_finalizes_exact_lease_only_after_telegram_message(monkeypatch):
    from diagnostic import delivery

    row = claimed_attempt()
    bot = sending_bot()
    monkeypatch.setattr(delivery.attempts, "claim_pending_delivery", AsyncMock(return_value=row))
    monkeypatch.setattr(delivery, "render_message", AsyncMock(return_value="ready"))
    finalized = AsyncMock(return_value=True)
    monkeypatch.setattr(delivery.attempts, "mark_delivery_sent", finalized)

    assert await delivery.deliver_attempt(
        bot, "attempt_123", settings=delivery_settings(), school=load_test_school()
    ) == "sent"

    bot.send_message.assert_awaited_once()
    assert bot.send_message.await_args.kwargs["chat_id"] == 42
    finalized.assert_awaited_once_with("attempt_123", row["pdf_locked_at"], 77)


@pytest.mark.asyncio
async def test_delivery_message_summarizes_the_result_and_opens_the_mini_app(monkeypatch):
    from diagnostic import delivery

    row = claimed_attempt()
    bot = sending_bot()
    monkeypatch.setattr(delivery.attempts, "claim_pending_delivery", AsyncMock(return_value=row))
    monkeypatch.setattr(delivery, "render_message", AsyncMock(return_value="Результат готов!"))
    monkeypatch.setattr(delivery.attempts, "mark_delivery_sent", AsyncMock(return_value=True))

    assert await delivery.deliver_attempt(
        bot, "attempt_123", settings=delivery_settings(), school=load_test_school()
    ) == "sent"

    kwargs = bot.send_message.await_args.kwargs
    assert "Результат готов!" in kwargs["text"]
    assert "Математика" in kwargs["text"]
    assert "2 из 2" in kwargs["text"]
    assert kwargs["parse_mode"] == "HTML"
    button = kwargs["reply_markup"].inline_keyboard[0][0]
    assert button.web_app.url == "https://miniapp.example.com/?attempt=attempt_123"


@pytest.mark.asyncio
async def test_delivery_message_escapes_a_hostile_subject(monkeypatch):
    from diagnostic import delivery

    row = claimed_attempt() | {"subject": "<b>Математика</b>"}
    bot = sending_bot()
    monkeypatch.setattr(delivery.attempts, "claim_pending_delivery", AsyncMock(return_value=row))
    monkeypatch.setattr(delivery, "render_message", AsyncMock(return_value="ready"))
    monkeypatch.setattr(delivery.attempts, "mark_delivery_sent", AsyncMock(return_value=True))

    assert await delivery.deliver_attempt(
        bot, "attempt_123", settings=delivery_settings(), school=load_test_school()
    ) == "sent"

    assert "&lt;b&gt;Математика&lt;/b&gt;" in bot.send_message.await_args.kwargs["text"]


@pytest.mark.asyncio
async def test_delivery_drops_the_intro_when_the_template_would_overflow(monkeypatch):
    from diagnostic import delivery

    row = claimed_attempt()
    bot = sending_bot()
    monkeypatch.setattr(delivery.attempts, "claim_pending_delivery", AsyncMock(return_value=row))
    monkeypatch.setattr(delivery, "render_message", AsyncMock(return_value="x" * 4096))
    monkeypatch.setattr(delivery.attempts, "mark_delivery_sent", AsyncMock(return_value=True))

    assert await delivery.deliver_attempt(
        bot, "attempt_123", settings=delivery_settings(), school=load_test_school()
    ) == "sent"

    text = bot.send_message.await_args.kwargs["text"]
    assert len(text) <= delivery.MESSAGE_LIMIT
    assert "x" * 4096 not in text
    assert "Математика" in text


@pytest.mark.asyncio
async def test_delivery_failure_stores_only_redacted_exception_class(monkeypatch):
    from diagnostic import delivery

    row = claimed_attempt()
    bot = SimpleNamespace(send_message=AsyncMock(side_effect=RuntimeError("token=secret")))
    monkeypatch.setattr(delivery.attempts, "claim_pending_delivery", AsyncMock(return_value=row))
    monkeypatch.setattr(delivery, "render_message", AsyncMock(return_value="ready"))
    failed = AsyncMock(return_value=True)
    monkeypatch.setattr(delivery.attempts, "mark_delivery_failed", failed)

    assert await delivery.deliver_attempt(
        bot, "attempt_123", settings=delivery_settings(), school=load_test_school()
    ) == "failed"
    failed.assert_awaited_once_with("attempt_123", row["pdf_locked_at"], "RuntimeError")


@pytest.mark.asyncio
async def test_delivery_configuration_failure_releases_lease_with_redacted_status(monkeypatch):
    from diagnostic import delivery

    row = claimed_attempt()
    monkeypatch.setattr(delivery.attempts, "claim_pending_delivery", AsyncMock(return_value=row))
    monkeypatch.setattr(delivery, "load_school", lambda: (_ for _ in ()).throw(ValueError("secret path")))
    failed = AsyncMock(return_value=True)
    monkeypatch.setattr(delivery.attempts, "mark_delivery_failed", failed)

    assert await delivery.deliver_attempt(
        SimpleNamespace(), "attempt_123", settings=delivery_settings()
    ) == "failed"
    failed.assert_awaited_once_with("attempt_123", row["pdf_locked_at"], "ValueError")


@pytest.mark.asyncio
async def test_delivery_stops_when_the_exact_lease_was_lost_before_sending(monkeypatch):
    from diagnostic import delivery

    row = claimed_attempt()
    bot = sending_bot()
    monkeypatch.setattr(delivery.attempts, "claim_pending_delivery", AsyncMock(return_value=row))
    monkeypatch.setattr(delivery, "render_message", AsyncMock(return_value="ready"))
    monkeypatch.setattr(
        delivery.attempts, "delivery_claim_is_active", AsyncMock(return_value=False)
    )

    assert await delivery.deliver_attempt(
        bot, "attempt_123", settings=delivery_settings(), school=load_test_school()
    ) == "failed"
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_delivery_deletes_external_message_when_exact_finalizer_loses(monkeypatch):
    from diagnostic import delivery

    row = claimed_attempt()
    bot = sending_bot(delete_message=AsyncMock())
    monkeypatch.setattr(delivery.attempts, "claim_pending_delivery", AsyncMock(return_value=row))
    monkeypatch.setattr(delivery, "render_message", AsyncMock(return_value="ready"))
    monkeypatch.setattr(delivery.attempts, "mark_delivery_sent", AsyncMock(return_value=False))

    assert await delivery.deliver_attempt(
        bot, "attempt_123", settings=delivery_settings(), school=load_test_school()
    ) == "failed"
    bot.delete_message.assert_awaited_once_with(chat_id=42, message_id=77)


@pytest.mark.asyncio
async def test_delivery_deletes_accepted_message_when_database_finalizer_raises(monkeypatch):
    from diagnostic import delivery

    row = claimed_attempt()
    bot = sending_bot(delete_message=AsyncMock())
    monkeypatch.setattr(delivery.attempts, "claim_pending_delivery", AsyncMock(return_value=row))
    monkeypatch.setattr(delivery, "render_message", AsyncMock(return_value="ready"))
    monkeypatch.setattr(
        delivery.attempts, "mark_delivery_sent", AsyncMock(side_effect=RuntimeError("db")),
    )
    monkeypatch.setattr(
        delivery.attempts, "delivery_is_sent", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(delivery.attempts, "mark_delivery_failed", AsyncMock(return_value=False))

    assert await delivery.deliver_attempt(
        bot, "attempt_123", settings=delivery_settings(), school=load_test_school()
    ) == "failed"
    bot.delete_message.assert_awaited_once_with(chat_id=42, message_id=77)


@pytest.mark.asyncio
async def test_delivery_keeps_message_when_finalizer_committed_before_connection_error(monkeypatch):
    from diagnostic import delivery

    row = claimed_attempt()
    bot = sending_bot(delete_message=AsyncMock())
    monkeypatch.setattr(delivery.attempts, "claim_pending_delivery", AsyncMock(return_value=row))
    monkeypatch.setattr(delivery, "render_message", AsyncMock(return_value="ready"))
    monkeypatch.setattr(
        delivery.attempts, "mark_delivery_sent", AsyncMock(side_effect=RuntimeError("lost response")),
    )
    monkeypatch.setattr(
        delivery.attempts, "delivery_is_sent", AsyncMock(return_value=True)
    )

    assert await delivery.deliver_attempt(
        bot, "attempt_123", settings=delivery_settings(), school=load_test_school()
    ) == "sent"
    bot.delete_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_delivery_reconciles_commit_error_when_cancelled_during_finalization(monkeypatch):
    from diagnostic import delivery

    row = claimed_attempt()
    finalizer_started = asyncio.Event()
    release_finalizer = asyncio.Event()

    async def commit_then_raise(*_):
        finalizer_started.set()
        await release_finalizer.wait()
        raise RuntimeError("lost response after commit")

    bot = sending_bot(delete_message=AsyncMock())
    monkeypatch.setattr(delivery.attempts, "claim_pending_delivery", AsyncMock(return_value=row))
    monkeypatch.setattr(delivery, "render_message", AsyncMock(return_value="ready"))
    monkeypatch.setattr(delivery.attempts, "mark_delivery_sent", commit_then_raise)
    sent_state = AsyncMock(return_value=True)
    monkeypatch.setattr(delivery.attempts, "delivery_is_sent", sent_state)
    failed = AsyncMock(return_value=False)
    monkeypatch.setattr(delivery.attempts, "mark_delivery_failed", failed)

    task = asyncio.create_task(
        delivery.deliver_attempt(
            bot, "attempt_123", settings=delivery_settings(), school=load_test_school()
        )
    )
    await finalizer_started.wait()
    task.cancel()
    release_finalizer.set()

    with pytest.raises(asyncio.CancelledError):
        await task
    sent_state.assert_awaited_once_with("attempt_123", 77)
    failed.assert_not_awaited()
    bot.delete_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_sent_finalizer_shields_status_verification_from_shutdown_cancellation():
    from diagnostic.delivery_state import reconcile_sent_finalizer

    verification_started = asyncio.Event()
    release_verification = asyncio.Event()

    async def commit_then_raise():
        raise RuntimeError("lost response after commit")

    async def verify_sent():
        verification_started.set()
        await release_verification.wait()
        return True

    finalizer = asyncio.create_task(commit_then_raise())
    task = asyncio.create_task(reconcile_sent_finalizer(finalizer, verify_sent))
    await verification_started.wait()
    task.cancel()
    release_verification.set()

    result = await task
    assert result.sent is True
    assert result.cancelled is True
    assert result.uncertain is False


@pytest.mark.asyncio
async def test_delivery_deletes_known_message_after_failure_finalizer_resolves_uncertainty(monkeypatch):
    from diagnostic import delivery

    row = claimed_attempt()
    bot = sending_bot(delete_message=AsyncMock())
    monkeypatch.setattr(delivery.attempts, "claim_pending_delivery", AsyncMock(return_value=row))
    monkeypatch.setattr(delivery, "render_message", AsyncMock(return_value="ready"))
    monkeypatch.setattr(
        delivery.attempts, "mark_delivery_sent", AsyncMock(side_effect=RuntimeError("db")),
    )
    monkeypatch.setattr(
        delivery.attempts, "delivery_is_sent", AsyncMock(side_effect=RuntimeError("db")),
    )
    monkeypatch.setattr(delivery.attempts, "mark_delivery_failed", AsyncMock(return_value=True))

    assert await delivery.deliver_attempt(
        bot, "attempt_123", settings=delivery_settings(), school=load_test_school()
    ) == "failed"
    bot.delete_message.assert_awaited_once_with(chat_id=42, message_id=77)


@pytest.mark.asyncio
@pytest.mark.parametrize("abandoned", [True, False])
async def test_abandonment_after_eight_attempts_alerts_without_private_detail(
    monkeypatch, abandoned
):
    from diagnostic import delivery

    row = claimed_attempt()
    alerted = []

    async def notify(kind, text):
        alerted.append((kind, text))

    bot = SimpleNamespace(send_message=AsyncMock(side_effect=ValueError("telegram")))
    monkeypatch.setattr(delivery.attempts, "claim_pending_delivery", AsyncMock(return_value=row))
    monkeypatch.setattr(delivery, "render_message", AsyncMock(return_value="ready"))
    monkeypatch.setattr(delivery.attempts, "mark_delivery_failed", AsyncMock(return_value=True))
    monkeypatch.setattr(
        delivery.attempts, "delivery_is_abandoned", AsyncMock(return_value=abandoned)
    )
    monkeypatch.setattr(delivery.alerts, "notify", notify)

    assert await delivery.deliver_attempt(
        bot, "attempt_123", settings=delivery_settings(), school=load_test_school()
    ) == "failed"
    assert alerted == (
        [("delivery_abandoned", "attempt=attempt_123 attempts=8 error=ValueError")]
        if abandoned
        else []
    )


@pytest.mark.asyncio
async def test_alert_failure_never_changes_the_delivery_outcome(monkeypatch):
    from diagnostic import delivery

    row = claimed_attempt()
    bot = SimpleNamespace(send_message=AsyncMock(side_effect=ValueError("telegram")))
    monkeypatch.setattr(delivery.attempts, "claim_pending_delivery", AsyncMock(return_value=row))
    monkeypatch.setattr(delivery, "render_message", AsyncMock(return_value="ready"))
    monkeypatch.setattr(delivery.attempts, "mark_delivery_failed", AsyncMock(return_value=True))
    monkeypatch.setattr(
        delivery.attempts,
        "delivery_is_abandoned",
        AsyncMock(side_effect=RuntimeError("database gone")),
    )

    assert await delivery.deliver_attempt(
        bot, "attempt_123", settings=delivery_settings(), school=load_test_school()
    ) == "failed"


@pytest.mark.asyncio
async def test_delivery_reports_empty_without_claim(monkeypatch):
    from diagnostic import delivery

    monkeypatch.setattr(delivery.attempts, "claim_pending_delivery", AsyncMock(return_value=None))

    assert await delivery.deliver_attempt(
        SimpleNamespace(), settings=delivery_settings()
    ) == "empty"


@pytest.mark.asyncio
async def test_deliver_attempt_by_id_always_closes_short_lived_bot(monkeypatch):
    from diagnostic import delivery

    session = SimpleNamespace(close=AsyncMock())
    monkeypatch.setattr(delivery.Settings, "from_env", lambda **_: SimpleNamespace(bot_token="123:test"))
    monkeypatch.setattr(delivery, "Bot", lambda **_: SimpleNamespace(session=session))
    monkeypatch.setattr(delivery, "deliver_attempt", AsyncMock(side_effect=RuntimeError("boom")))

    with pytest.raises(RuntimeError, match="boom"):
        await delivery.deliver_attempt_by_id("attempt_123")
    session.close.assert_awaited_once()
