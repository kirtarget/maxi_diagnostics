from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_emit_event_filters_action_and_data_to_strict_allowlists(monkeypatch):
    from diagnostic import analytics

    post = AsyncMock()
    monkeypatch.setattr(analytics.Settings, "from_env", lambda **_: SimpleNamespace(analytics_webhook_url="https://analytics.example/events"))
    monkeypatch.setattr(analytics, "_post_json", post)

    await analytics.emit_event("diagnostic_completed", 42, {"diagnostic_id": "demo-math", "mode": "quick", "question_index": 2, "result_status": "completed", "delivery_status": "pending", "score": 100, "kind": "secret", "status": {"answers": {"q1": "secret"}}, "answers": {"q1": "secret"}, "email": "a@example.test", "text": "secret"})
    await analytics.emit_event("arbitrary_action", 42, {"diagnostic_id": "demo-math"})

    post.assert_awaited_once_with("https://analytics.example/events", {"action": "diagnostic_completed", "data": {"diagnostic_id": "demo-math", "mode": "quick", "question_index": 2, "result_status": "completed", "delivery_status": "pending"}}, timeout=5)


@pytest.mark.asyncio
async def test_emit_event_is_noop_without_url_and_swallows_transport_failure(monkeypatch):
    from diagnostic import analytics

    post = AsyncMock(side_effect=RuntimeError("secret webhook failed"))
    monkeypatch.setattr(analytics, "_post_json", post)
    monkeypatch.setattr(analytics.Settings, "from_env", lambda **_: SimpleNamespace(analytics_webhook_url=None))
    await analytics.emit_event("diagnostic_completed", 42, {})
    post.assert_not_awaited()

    monkeypatch.setattr(analytics.Settings, "from_env", lambda **_: SimpleNamespace(analytics_webhook_url="https://analytics.example/events"))
    await analytics.emit_event("diagnostic_completed", 42, {})
    post.assert_awaited_once()
