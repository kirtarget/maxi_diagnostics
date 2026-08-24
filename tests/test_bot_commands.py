from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from diagnostic.catalog import load_catalog
from diagnostic.school import load_school
from diagnostic.settings import Settings


def _settings() -> Settings:
    return Settings(
        database_url="postgresql://test",
        bot_token="123456:test-token",
        miniapp_url="https://diagnostic.school.example/app",
        miniapp_origin="https://diagnostic.school.example",
        admin_username="admin",
        admin_password="password",
        analytics_webhook_url=None,
    )


def test_bot_command_menu_is_diagnostic_only():
    from diagnostic.bot.main import build_bot_commands

    assert [item.command for item in build_bot_commands(load_school())] == [
        "start",
        "diagnostics",
        "results",
        "plan",
    ]


@pytest.mark.asyncio
async def test_results_handler_reads_only_telegram_users_results(monkeypatch):
    from diagnostic.bot import handlers

    list_completed = AsyncMock(return_value=[])
    monkeypatch.setattr(handlers.attempts, "list_completed_attempts", list_completed)
    monkeypatch.setattr(
        handlers,
        "render_message",
        AsyncMock(return_value="No completed diagnostics."),
    )
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=731),
        answer=AsyncMock(),
    )

    await handlers.send_results(message, _settings(), load_school(), load_catalog(load_school()))

    list_completed.assert_awaited_once_with(731)
    message.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_result_callback_scopes_attempt_to_telegram_user_and_acknowledges(monkeypatch):
    from diagnostic.bot import handlers

    get_attempt = AsyncMock(return_value=None)
    monkeypatch.setattr(handlers.attempts, "get_attempt", get_attempt)
    callback = SimpleNamespace(
        data="diag:result:attempt-1",
        from_user=SimpleNamespace(id=902),
        answer=AsyncMock(),
        message=SimpleNamespace(answer=AsyncMock()),
    )

    await handlers.show_result(callback, _settings(), load_school(), load_catalog(load_school()))

    get_attempt.assert_awaited_once_with("attempt-1", 902)
    callback.answer.assert_awaited_once_with(
        load_school().brand.interface.result_not_found, show_alert=True
    )


@pytest.mark.asyncio
async def test_optional_command_configuration_failure_does_not_prevent_polling_startup():
    from diagnostic.bot.main import configure_bot_safely

    bot = SimpleNamespace(
        set_my_commands=AsyncMock(side_effect=RuntimeError("telegram unavailable")),
        delete_webhook=AsyncMock(return_value=True),
    )

    await configure_bot_safely(bot, load_school())

    bot.set_my_commands.assert_awaited_once()
    bot.delete_webhook.assert_awaited_once_with(drop_pending_updates=False)


@pytest.mark.asyncio
async def test_webhook_cleanup_failure_aborts_startup_so_restart_can_retry():
    from diagnostic.bot.main import configure_bot_safely

    bot = SimpleNamespace(
        set_my_commands=AsyncMock(return_value=True),
        delete_webhook=AsyncMock(side_effect=RuntimeError("telegram unavailable")),
    )

    with pytest.raises(RuntimeError, match="telegram_delete_webhook_failed"):
        await configure_bot_safely(bot, load_school())


@pytest.mark.asyncio
async def test_plan_marks_displayed_result_viewed_and_emits_transition_event(monkeypatch):
    from diagnostic.bot import handlers

    row = {
        "attempt_id": "attempt-1", "diagnostic_id": "demo-math", "subject": "Математика",
        "mode": "full", "strong_topics": ["Алгебра"], "growth_topics": ["Геометрия"],
    }
    monkeypatch.setattr(handlers.attempts, "list_completed_attempts", AsyncMock(return_value=[row]))
    viewed = AsyncMock(return_value=row | {"viewed_transition": True})
    monkeypatch.setattr(handlers.attempts, "mark_result_viewed", viewed)
    fired = Mock()
    monkeypatch.setattr(handlers, "fire_event", fired)
    message = SimpleNamespace(from_user=SimpleNamespace(id=731), answer=AsyncMock())

    await handlers.send_plan(message, _settings(), load_school(), load_catalog(load_school()))

    message.answer.assert_awaited_once()
    viewed.assert_awaited_once_with("attempt-1", 731)
    fired.assert_called_once_with(
        "diagnostic_result_viewed", 731, {"attempt_id": "attempt-1"}
    )


@pytest.mark.asyncio
async def test_start_handles_temporary_erasure_barrier_with_safe_message(monkeypatch):
    from diagnostic.bot import handlers

    monkeypatch.setattr(
        handlers.attempts, "mark_opened",
        AsyncMock(side_effect=ValueError("diagnostic_user_erased")),
    )
    monkeypatch.setattr(handlers, "render_message", AsyncMock(return_value="Data erased"))
    message = SimpleNamespace(from_user=SimpleNamespace(id=731), answer=AsyncMock())

    await handlers.send_home(message, _settings(), load_school(), load_catalog(load_school()))

    message.answer.assert_awaited_once_with(
        "Data erased", parse_mode="HTML", disable_web_page_preview=True,
    )


@pytest.mark.asyncio
async def test_polling_failure_closes_bot_session_and_database(monkeypatch):
    from diagnostic.bot import main as bot_main

    events: list[str] = []
    settings = _settings()
    school = load_school()
    catalog = load_catalog(school)

    class FakeBot:
        def __init__(self, *, token: str):
            assert token == settings.bot_token
            self.session = SimpleNamespace(close=AsyncMock(side_effect=lambda: events.append("bot_closed")))

    class FakeDispatcher:
        def include_router(self, _router):
            events.append("router_included")

        def resolve_used_update_types(self):
            return ["message", "callback_query"]

        async def start_polling(self, _bot, *, allowed_updates):
            assert allowed_updates == ["message", "callback_query"]
            events.append("polling")
            raise RuntimeError("polling failed")

    class FakeScheduler:
        running = False

        def start(self):
            self.running = True
            events.append("scheduler_started")

        def shutdown(self, *, wait):
            assert wait is False
            self.running = False
            events.append("scheduler_stopped")

    monkeypatch.setattr(bot_main.Settings, "from_env", lambda **_: settings)
    monkeypatch.setattr(bot_main, "load_school", lambda: school)
    monkeypatch.setattr(bot_main, "load_catalog", lambda actual: catalog)
    monkeypatch.setattr(
        bot_main,
        "init_db",
        AsyncMock(side_effect=lambda *_: events.append("database_initialized")),
    )
    monkeypatch.setattr(
        bot_main,
        "close_db",
        AsyncMock(side_effect=lambda: events.append("database_closed")),
    )
    monkeypatch.setattr(bot_main, "configure_bot_safely", AsyncMock())
    monkeypatch.setattr(bot_main, "store_report_asset_bundle", AsyncMock())
    monkeypatch.setattr(bot_main, "Bot", FakeBot)
    monkeypatch.setattr(bot_main, "Dispatcher", FakeDispatcher)
    monkeypatch.setattr(
        bot_main,
        "build_worker_scheduler",
        lambda actual_bot, actual_settings, actual_school, actual_catalog: FakeScheduler(),
    )

    with pytest.raises(RuntimeError, match="polling failed"):
        await bot_main.main()

    assert events == [
        "database_initialized",
        "router_included",
        "scheduler_started",
        "polling",
        "scheduler_stopped",
        "bot_closed",
        "database_closed",
    ]


@pytest.mark.asyncio
async def test_delivery_only_mode_runs_scheduler_without_starting_polling(monkeypatch):
    from diagnostic.bot import main as bot_main

    events: list[str] = []
    settings = replace(_settings(), bot_polling_enabled=False)
    school = load_school()
    catalog = load_catalog(school)

    class FakeBot:
        def __init__(self, *, token: str):
            assert token == settings.bot_token
            self.session = SimpleNamespace(
                close=AsyncMock(side_effect=lambda: events.append("bot_closed"))
            )

    class FakeScheduler:
        running = False

        def start(self):
            self.running = True
            events.append("scheduler_started")

        def shutdown(self, *, wait):
            assert wait is False
            self.running = False
            events.append("scheduler_stopped")

    monkeypatch.setattr(bot_main.Settings, "from_env", lambda **_: settings)
    monkeypatch.setattr(bot_main, "load_school", lambda: school)
    monkeypatch.setattr(bot_main, "load_catalog", lambda actual: catalog)
    monkeypatch.setattr(bot_main, "init_db", AsyncMock())
    monkeypatch.setattr(bot_main, "close_db", AsyncMock())
    monkeypatch.setattr(bot_main, "store_report_asset_bundle", AsyncMock())
    monkeypatch.setattr(bot_main, "Bot", FakeBot)
    monkeypatch.setattr(
        bot_main,
        "Dispatcher",
        Mock(side_effect=AssertionError("polling dispatcher must not start")),
    )
    monkeypatch.setattr(
        bot_main,
        "build_worker_scheduler",
        lambda actual_bot, actual_settings, actual_school, actual_catalog: FakeScheduler(),
    )
    monkeypatch.setattr(
        bot_main,
        "wait_for_worker_shutdown",
        AsyncMock(side_effect=lambda: events.append("worker_wait")),
    )

    await bot_main.main()

    assert events == [
        "scheduler_started",
        "worker_wait",
        "scheduler_stopped",
        "bot_closed",
    ]
