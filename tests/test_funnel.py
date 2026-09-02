from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from diagnostic.db import funnel
from diagnostic.session_identity import session_subject_key


@pytest.mark.asyncio
async def test_record_event_rejects_unknown_actions_without_touching_the_database(monkeypatch):
    pool = AsyncMock()
    monkeypatch.setattr(funnel, "get_pool", AsyncMock(return_value=pool))

    assert await funnel.record_event(
        application_secret="stable-secret", user_id=42, action="deleted_account"
    ) is False
    pool.acquire.assert_not_called()


@pytest.mark.asyncio
async def test_record_event_never_raises_into_the_caller(monkeypatch, caplog):
    monkeypatch.setattr(
        funnel, "get_pool", AsyncMock(side_effect=RuntimeError("database_unavailable"))
    )

    with caplog.at_level("WARNING"):
        recorded = await funnel.record_event(
            application_secret="stable-secret", user_id=42, action="opened"
        )

    assert recorded is False
    assert "diagnostic_funnel_event_failed action=opened" in caplog.text
    assert "database_unavailable" not in caplog.text


@pytest.mark.asyncio
async def test_record_event_stores_only_the_subject_hash_and_bounded_labels(monkeypatch):
    executed: list[tuple] = []

    class _Connection:
        async def execute(self, sql, *arguments):
            executed.append((" ".join(sql.split()), arguments))

    class _Acquire:
        async def __aenter__(self):
            return _Connection()

        async def __aexit__(self, *_):
            return False

    monkeypatch.setattr(
        funnel, "get_pool", AsyncMock(return_value=SimpleNamespace(acquire=_Acquire))
    )

    assert await funnel.record_event(
        application_secret="stable-secret",
        user_id=42,
        action="started",
        exam="e" * 64,
        subject="  ",
    ) is True

    sql, arguments = executed[0]
    assert sql.startswith("INSERT INTO diagnostic_funnel_events")
    assert "user_id" not in sql
    subject_hash, action, exam, subject = arguments
    assert subject_hash == session_subject_key("stable-secret", 42)
    assert action == "started"
    assert exam == "e" * 32
    assert subject is None


@pytest.mark.parametrize("days", [0, 1, 14, 90])
def test_window_days_accepts_only_the_documented_windows(days):
    with pytest.raises(ValueError, match="funnel_window_invalid"):
        funnel._window_days(days)


def test_window_sql_filters_are_parameterized_and_bounded():
    assert "$1::int" in funnel._SUMMARY_SQL
    assert "$2::text IS NULL OR exam = $2::text" in funnel._SUMMARY_SQL
    assert "LIMIT 200" in funnel._BREAKDOWN_SQL
    for action in funnel.FUNNEL_ACTIONS:
        assert f"'{action}'" in funnel._SUMMARY_SQL
