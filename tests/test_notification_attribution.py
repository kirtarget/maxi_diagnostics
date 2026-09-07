from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit

import pytest

from diagnostic import notification_attribution as attribution


def make_token():
    url = attribution.notification_url(
        "https://app.example/?source=telegram", "secret", 42, 9,
        datetime(2026, 9, 6, tzinfo=timezone.utc),
    )
    query = parse_qs(urlsplit(url).query)
    assert query["source"] == ["telegram"]
    return query["n"][0]


def test_notification_token_is_bound_to_recipient_and_secret():
    token = make_token()
    assert attribution.verify_token(token, "secret", 42) == (9, 1788652800)
    assert attribution.verify_token(token, "secret", 43) is None
    assert attribution.verify_token(token, "other", 42) is None
    assert attribution.verify_token("10" + token[1:], "secret", 42) is None
    assert attribution.verify_token("invalid", "secret", 42) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("delivered", [False, True])
async def test_open_requires_delivered_owned_notification(monkeypatch, delivered):
    connection = SimpleNamespace(fetchval=AsyncMock(return_value=delivered))

    class Acquire:
        async def __aenter__(self):
            return connection

        async def __aexit__(self, *_):
            return False

    monkeypatch.setattr(attribution, "get_pool", AsyncMock(return_value=SimpleNamespace(acquire=Acquire)))
    record = AsyncMock(return_value=True)
    monkeypatch.setattr(attribution.funnel, "record_event", record)
    assert await attribution.record_open(make_token(), "secret", 42) is delivered
    assert connection.fetchval.await_args.args[1:] == (9, 42, 1788652800)
    if delivered:
        assert record.await_args.kwargs["action"] == "notification_opened"
        assert record.await_args.kwargs["dedupe_key"] == "9/1788652800"
    else:
        record.assert_not_awaited()


@pytest.mark.asyncio
async def test_forged_notification_token_does_not_query_database(monkeypatch):
    pool = AsyncMock()
    monkeypatch.setattr(attribution, "get_pool", pool)
    assert not await attribution.record_open(make_token(), "secret", 99)
    pool.assert_not_awaited()
