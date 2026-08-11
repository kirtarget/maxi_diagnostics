from __future__ import annotations

from datetime import datetime, timezone
import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest


@pytest.fixture(autouse=True)
def active_pdf_claim(monkeypatch):
    from diagnostic import delivery

    monkeypatch.setattr(
        delivery.attempts, "pdf_claim_is_active", AsyncMock(return_value=True)
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


@pytest.mark.asyncio
async def test_delivery_finalizes_exact_lease_only_after_telegram_message(monkeypatch):
    from diagnostic import delivery

    row = claimed_attempt()
    bot = SimpleNamespace(send_document=AsyncMock(return_value=SimpleNamespace(message_id=77)))
    monkeypatch.setattr(delivery.attempts, "claim_pending_pdf", AsyncMock(return_value=row))
    monkeypatch.setattr(delivery, "build_report", lambda *_: b"%PDF-report")
    monkeypatch.setattr(delivery, "render_message", AsyncMock(return_value="ready"))
    monkeypatch.setattr(delivery, "load_school", lambda: SimpleNamespace())
    monkeypatch.setattr(delivery, "load_catalog", lambda _: SimpleNamespace())
    finalized = AsyncMock(return_value=True)
    monkeypatch.setattr(delivery.attempts, "mark_pdf_delivered", finalized)
    monkeypatch.setattr(
        delivery.attempts, "store_pdf_document", AsyncMock(return_value=True)
    )

    assert await delivery.deliver_attempt(bot, "attempt_123") == "sent"

    bot.send_document.assert_awaited_once()
    assert bot.send_document.await_args.kwargs["chat_id"] == 42
    finalized.assert_awaited_once_with("attempt_123", row["pdf_locked_at"], 77)


@pytest.mark.asyncio
async def test_delivery_failure_stores_only_redacted_exception_class(monkeypatch):
    from diagnostic import delivery

    row = claimed_attempt()
    bot = SimpleNamespace(send_document=AsyncMock(side_effect=RuntimeError("token=secret")))
    monkeypatch.setattr(delivery.attempts, "claim_pending_pdf", AsyncMock(return_value=row))
    monkeypatch.setattr(delivery, "build_report", lambda *_: b"%PDF-report")
    monkeypatch.setattr(delivery, "render_message", AsyncMock(return_value="ready"))
    monkeypatch.setattr(delivery, "load_school", lambda: SimpleNamespace())
    monkeypatch.setattr(delivery, "load_catalog", lambda _: SimpleNamespace())
    failed = AsyncMock(return_value=True)
    monkeypatch.setattr(delivery.attempts, "mark_pdf_failed", failed)
    monkeypatch.setattr(
        delivery.attempts, "store_pdf_document", AsyncMock(return_value=True)
    )

    assert await delivery.deliver_attempt(bot, "attempt_123") == "failed"
    failed.assert_awaited_once_with("attempt_123", row["pdf_locked_at"], "RuntimeError")


@pytest.mark.asyncio
async def test_delivery_configuration_failure_releases_lease_with_redacted_status(monkeypatch):
    from diagnostic import delivery

    row = claimed_attempt()
    monkeypatch.setattr(delivery.attempts, "claim_pending_pdf", AsyncMock(return_value=row))
    monkeypatch.setattr(delivery, "load_school", lambda: (_ for _ in ()).throw(ValueError("secret path")))
    failed = AsyncMock(return_value=True)
    monkeypatch.setattr(delivery.attempts, "mark_pdf_failed", failed)

    assert await delivery.deliver_attempt(SimpleNamespace(), "attempt_123") == "failed"
    failed.assert_awaited_once_with("attempt_123", row["pdf_locked_at"], "ValueError")


@pytest.mark.asyncio
async def test_delivery_builds_pdf_without_blocking_the_event_loop(monkeypatch):
    from diagnostic import delivery

    row = claimed_attempt()
    bot = SimpleNamespace(send_document=AsyncMock(return_value=SimpleNamespace(message_id=77)))
    monkeypatch.setattr(delivery.attempts, "claim_pending_pdf", AsyncMock(return_value=row))
    monkeypatch.setattr(delivery, "load_school", lambda: SimpleNamespace())
    monkeypatch.setattr(delivery, "load_catalog", lambda _: SimpleNamespace())
    monkeypatch.setattr(delivery, "render_message", AsyncMock(return_value="ready"))
    monkeypatch.setattr(delivery.attempts, "store_pdf_document", AsyncMock(return_value=True))
    monkeypatch.setattr(delivery.attempts, "mark_pdf_delivered", AsyncMock(return_value=True))

    def slow_report(*_):
        time.sleep(0.08)
        return b"%PDF-report"

    monkeypatch.setattr(delivery, "build_report", slow_report)
    loop = asyncio.get_running_loop()
    started = loop.time()
    callback_times = []
    loop.call_later(0.01, lambda: callback_times.append(loop.time()))

    assert await delivery.deliver_attempt(bot, "attempt_123") == "sent"

    assert callback_times
    assert callback_times[0] - started < 0.05


@pytest.mark.asyncio
async def test_delivery_uses_one_document_call_for_an_oversized_template(monkeypatch):
    from diagnostic import delivery

    row = claimed_attempt()
    bot = SimpleNamespace(send_document=AsyncMock(return_value=SimpleNamespace(message_id=77)))
    monkeypatch.setattr(delivery.attempts, "claim_pending_pdf", AsyncMock(return_value=row))
    monkeypatch.setattr(delivery, "build_report", lambda *_: b"%PDF-report")
    monkeypatch.setattr(delivery, "render_message", AsyncMock(return_value="x" * 1025))
    monkeypatch.setattr(delivery, "load_school", lambda: load_test_school())
    monkeypatch.setattr(delivery, "load_catalog", lambda _: SimpleNamespace())
    monkeypatch.setattr(delivery.attempts, "store_pdf_document", AsyncMock(return_value=True))
    monkeypatch.setattr(delivery.attempts, "mark_pdf_delivered", AsyncMock(return_value=True))

    assert await delivery.deliver_attempt(bot, "attempt_123") == "sent"
    bot.send_document.assert_awaited_once()
    assert "caption" not in bot.send_document.await_args.kwargs


@pytest.mark.asyncio
async def test_delivery_omits_caption_when_escaped_fallback_would_be_too_long(monkeypatch):
    from diagnostic import delivery

    row = claimed_attempt() | {"subject": "&" * 128}
    bot = SimpleNamespace(send_document=AsyncMock(return_value=SimpleNamespace(message_id=77)))
    monkeypatch.setattr(delivery.attempts, "claim_pending_pdf", AsyncMock(return_value=row))
    monkeypatch.setattr(delivery, "build_report", lambda *_: b"%PDF-report")
    monkeypatch.setattr(delivery, "render_message", AsyncMock(return_value="&" * 1025))
    monkeypatch.setattr(delivery, "load_school", load_test_school)
    monkeypatch.setattr(delivery, "load_catalog", lambda _: SimpleNamespace())
    monkeypatch.setattr(delivery.attempts, "store_pdf_document", AsyncMock(return_value=True))
    monkeypatch.setattr(delivery.attempts, "mark_pdf_delivered", AsyncMock(return_value=True))

    assert await delivery.deliver_attempt(bot, "attempt_123") == "sent"
    assert "caption" not in bot.send_document.await_args.kwargs


@pytest.mark.asyncio
async def test_delivery_deletes_external_message_when_exact_finalizer_loses(monkeypatch):
    from diagnostic import delivery

    row = claimed_attempt()
    bot = SimpleNamespace(
        send_document=AsyncMock(return_value=SimpleNamespace(message_id=77)),
        delete_message=AsyncMock(),
    )
    monkeypatch.setattr(delivery.attempts, "claim_pending_pdf", AsyncMock(return_value=row))
    monkeypatch.setattr(delivery, "build_report", lambda *_: b"%PDF-report")
    monkeypatch.setattr(delivery, "render_message", AsyncMock(return_value="ready"))
    monkeypatch.setattr(delivery, "load_school", lambda: SimpleNamespace())
    monkeypatch.setattr(delivery, "load_catalog", lambda _: SimpleNamespace())
    monkeypatch.setattr(delivery.attempts, "store_pdf_document", AsyncMock(return_value=True))
    monkeypatch.setattr(delivery.attempts, "mark_pdf_delivered", AsyncMock(return_value=False))

    assert await delivery.deliver_attempt(bot, "attempt_123") == "failed"
    bot.delete_message.assert_awaited_once_with(chat_id=42, message_id=77)


@pytest.mark.asyncio
async def test_delivery_deletes_accepted_message_when_database_finalizer_raises(monkeypatch):
    from diagnostic import delivery

    row = claimed_attempt()
    bot = SimpleNamespace(
        send_document=AsyncMock(return_value=SimpleNamespace(message_id=77)),
        delete_message=AsyncMock(),
    )
    monkeypatch.setattr(delivery.attempts, "claim_pending_pdf", AsyncMock(return_value=row))
    monkeypatch.setattr(delivery, "build_report", lambda *_: b"%PDF-report")
    monkeypatch.setattr(delivery, "render_message", AsyncMock(return_value="ready"))
    monkeypatch.setattr(delivery, "load_school", lambda: SimpleNamespace())
    monkeypatch.setattr(delivery, "load_catalog", lambda _: SimpleNamespace())
    monkeypatch.setattr(delivery.attempts, "store_pdf_document", AsyncMock(return_value=True))
    monkeypatch.setattr(
        delivery.attempts, "mark_pdf_delivered", AsyncMock(side_effect=RuntimeError("db")),
    )
    monkeypatch.setattr(
        delivery.attempts, "pdf_delivery_is_sent", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(delivery.attempts, "mark_pdf_failed", AsyncMock(return_value=False))

    assert await delivery.deliver_attempt(bot, "attempt_123") == "failed"
    bot.delete_message.assert_awaited_once_with(chat_id=42, message_id=77)


@pytest.mark.asyncio
async def test_delivery_keeps_message_when_finalizer_committed_before_connection_error(monkeypatch):
    from diagnostic import delivery

    row = claimed_attempt()
    bot = SimpleNamespace(
        send_document=AsyncMock(return_value=SimpleNamespace(message_id=77)),
        delete_message=AsyncMock(),
    )
    monkeypatch.setattr(delivery.attempts, "claim_pending_pdf", AsyncMock(return_value=row))
    monkeypatch.setattr(delivery, "build_report", lambda *_: b"%PDF-report")
    monkeypatch.setattr(delivery, "render_message", AsyncMock(return_value="ready"))
    monkeypatch.setattr(delivery, "load_school", lambda: SimpleNamespace())
    monkeypatch.setattr(delivery, "load_catalog", lambda _: SimpleNamespace())
    monkeypatch.setattr(delivery.attempts, "store_pdf_document", AsyncMock(return_value=True))
    monkeypatch.setattr(
        delivery.attempts, "mark_pdf_delivered", AsyncMock(side_effect=RuntimeError("lost response")),
    )
    monkeypatch.setattr(
        delivery.attempts, "pdf_delivery_is_sent", AsyncMock(return_value=True)
    )

    assert await delivery.deliver_attempt(bot, "attempt_123") == "sent"
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

    bot = SimpleNamespace(
        send_document=AsyncMock(return_value=SimpleNamespace(message_id=77)),
        delete_message=AsyncMock(),
    )
    monkeypatch.setattr(delivery.attempts, "claim_pending_pdf", AsyncMock(return_value=row))
    monkeypatch.setattr(delivery, "build_report", lambda *_: b"%PDF-report")
    monkeypatch.setattr(delivery, "render_message", AsyncMock(return_value="ready"))
    monkeypatch.setattr(delivery, "load_school", lambda: SimpleNamespace())
    monkeypatch.setattr(delivery, "load_catalog", lambda _: SimpleNamespace())
    monkeypatch.setattr(delivery.attempts, "store_pdf_document", AsyncMock(return_value=True))
    monkeypatch.setattr(delivery.attempts, "mark_pdf_delivered", commit_then_raise)
    sent_state = AsyncMock(return_value=True)
    monkeypatch.setattr(delivery.attempts, "pdf_delivery_is_sent", sent_state)
    failed = AsyncMock(return_value=False)
    monkeypatch.setattr(delivery.attempts, "mark_pdf_failed", failed)

    task = asyncio.create_task(delivery.deliver_attempt(bot, "attempt_123"))
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
    bot = SimpleNamespace(
        send_document=AsyncMock(return_value=SimpleNamespace(message_id=77)),
        delete_message=AsyncMock(),
    )
    monkeypatch.setattr(delivery.attempts, "claim_pending_pdf", AsyncMock(return_value=row))
    monkeypatch.setattr(delivery, "build_report", lambda *_: b"%PDF-report")
    monkeypatch.setattr(delivery, "render_message", AsyncMock(return_value="ready"))
    monkeypatch.setattr(delivery, "load_school", lambda: SimpleNamespace())
    monkeypatch.setattr(delivery, "load_catalog", lambda _: SimpleNamespace())
    monkeypatch.setattr(delivery.attempts, "store_pdf_document", AsyncMock(return_value=True))
    monkeypatch.setattr(
        delivery.attempts, "mark_pdf_delivered", AsyncMock(side_effect=RuntimeError("db")),
    )
    monkeypatch.setattr(
        delivery.attempts, "pdf_delivery_is_sent", AsyncMock(side_effect=RuntimeError("db")),
    )
    monkeypatch.setattr(delivery.attempts, "mark_pdf_failed", AsyncMock(return_value=True))

    assert await delivery.deliver_attempt(bot, "attempt_123") == "failed"
    bot.delete_message.assert_awaited_once_with(chat_id=42, message_id=77)


@pytest.mark.asyncio
async def test_delivery_reports_empty_without_claim(monkeypatch):
    from diagnostic import delivery

    monkeypatch.setattr(delivery.attempts, "claim_pending_pdf", AsyncMock(return_value=None))

    assert await delivery.deliver_attempt(SimpleNamespace()) == "empty"


@pytest.mark.asyncio
@pytest.mark.parametrize("bundle", [None, b"wrong-bundle"])
async def test_delivery_rejects_missing_or_mismatched_frozen_asset_bundle(monkeypatch, bundle):
    from diagnostic import delivery

    row = claimed_attempt() | {"report_asset_bundle_id": "0" * 64}
    build = Mock()
    failed = AsyncMock(return_value=True)
    monkeypatch.setattr(delivery.attempts, "claim_pending_pdf", AsyncMock(return_value=row))
    monkeypatch.setattr(delivery.attempts, "get_report_asset_bundle", AsyncMock(return_value=bundle))
    monkeypatch.setattr(delivery.attempts, "mark_pdf_failed", failed)
    monkeypatch.setattr(delivery, "build_report", build)

    assert await delivery.deliver_attempt(SimpleNamespace(), "attempt_123") == "failed"
    build.assert_not_called()
    failed.assert_awaited_once_with("attempt_123", row["pdf_locked_at"], "ValueError")


@pytest.mark.asyncio
async def test_delivery_retry_uses_stored_pdf_without_loading_large_asset_bundle(monkeypatch):
    from diagnostic import delivery

    row = claimed_attempt() | {
        "pdf_document": b"%PDF-stored",
        "report_asset_bundle_id": "0" * 64,
    }
    get_bundle = AsyncMock()
    build = Mock()
    bot = SimpleNamespace(
        send_document=AsyncMock(return_value=SimpleNamespace(message_id=77)),
    )
    monkeypatch.setattr(delivery.attempts, "claim_pending_pdf", AsyncMock(return_value=row))
    monkeypatch.setattr(delivery.attempts, "get_report_asset_bundle", get_bundle)
    monkeypatch.setattr(delivery.attempts, "mark_pdf_delivered", AsyncMock(return_value=True))
    monkeypatch.setattr(delivery, "build_report", build)
    monkeypatch.setattr(delivery, "render_message", AsyncMock(return_value="ready"))
    monkeypatch.setattr(delivery, "load_school", lambda: SimpleNamespace())

    assert await delivery.deliver_attempt(bot, "attempt_123") == "sent"
    get_bundle.assert_not_awaited()
    build.assert_not_called()


def load_test_school():
    from pathlib import Path
    from diagnostic.school import load_school

    return load_school(Path(__file__).resolve().parents[1] / "tests/fixtures/sample-school")


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
