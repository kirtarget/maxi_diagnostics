from __future__ import annotations

import logging

import pytest

from diagnostic import alerts


class FakeBot:
    def __init__(self, failures: int = 0):
        self.sent: list[dict] = []
        self.failures = failures

    async def send_message(self, **kwargs):
        self.sent.append(kwargs)
        if self.failures:
            self.failures -= 1
            raise RuntimeError("telegram_unavailable token=secret")
        return object()


@pytest.fixture(autouse=True)
def isolated_alerts():
    alerts.reset()
    yield
    alerts.reset()


@pytest.mark.asyncio
async def test_alerting_is_disabled_without_a_configured_chat():
    bot = FakeBot()
    alerts.configure(bot, None)

    await alerts.notify("pdf_abandoned", "attempt=attempt_123 attempts=8")

    assert bot.sent == []


@pytest.mark.asyncio
async def test_one_message_per_kind_per_hour_and_other_kinds_still_pass(monkeypatch):
    bot = FakeBot()
    alerts.configure(bot, -100200300)
    clock = [1_000.0]
    monkeypatch.setattr(alerts.time, "monotonic", lambda: clock[0])

    await alerts.notify("pdf_abandoned", "attempt=a1 attempts=8")
    await alerts.notify("pdf_abandoned", "attempt=a2 attempts=8")
    await alerts.notify("followup_abandoned", "notification=7 attempts=8")
    clock[0] += alerts.DEDUPE_WINDOW_SECONDS - 1
    await alerts.notify("pdf_abandoned", "attempt=a3 attempts=8")
    clock[0] += 2
    await alerts.notify("pdf_abandoned", "attempt=a4 attempts=8")

    assert [message["text"] for message in bot.sent] == [
        "pdf_abandoned: attempt=a1 attempts=8",
        "followup_abandoned: notification=7 attempts=8",
        "pdf_abandoned: attempt=a4 attempts=8",
    ]
    assert all(message["chat_id"] == -100200300 for message in bot.sent)


@pytest.mark.asyncio
async def test_send_failure_is_logged_without_the_transport_error_text(caplog):
    alerts.configure(FakeBot(failures=1), 4242)

    with caplog.at_level(logging.WARNING):
        await alerts.notify("worker_tick_failed", "error=RuntimeError: database gone")

    assert "diagnostic_alert_failed kind=worker_tick_failed error=RuntimeError" in caplog.text
    assert "secret" not in caplog.text


@pytest.mark.asyncio
async def test_alert_text_is_bounded():
    bot = FakeBot()
    alerts.configure(bot, 4242)

    await alerts.notify("worker_tick_failed", "x" * 5_000)

    assert len(bot.sent[0]["text"]) == alerts.MAX_TEXT_LENGTH
