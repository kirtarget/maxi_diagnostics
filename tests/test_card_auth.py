import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from diagnostic.api.card_results import create_card_results_router
from diagnostic.api.dependencies import request_user
from diagnostic.api.league import LeagueRequest
from diagnostic.api.models import ApiRequest
from diagnostic.card_auth import card_user_id, verify_card_ticket

CARD = "11111111-2222-3333-4444-555555555555"


def ticket(data=None, secret="test-secret"):
    raw = json.dumps(data or {"c": CARD, "e": 4102444800}, separators=(",", ":")).encode()
    payload = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    signed = "v1." + payload
    signature = base64.urlsafe_b64encode(hmac.digest(secret.encode(), signed.encode(), "sha256")).decode().rstrip("=")
    return signed + "." + signature


def test_fixed_vector_and_identity():
    assert ticket() == "v1.eyJjIjoiMTExMTExMTEtMjIyMi0zMzMzLTQ0NDQtNTU1NTU1NTU1NTU1IiwiZSI6NDEwMjQ0NDgwMH0.pcygmbtA0M33p-qZrbcMqfWs_W8Mn9PSD-P75scl6DI"
    assert verify_card_ticket(ticket(), "test-secret", now=1) == CARD
    digest = hashlib.sha256(("admission-card:" + CARD).encode()).digest()
    assert card_user_id(CARD) == -((int.from_bytes(digest[:8], "big") >> 2) + 1)
    assert -(2**62) <= card_user_id(CARD) <= -1
    assert card_user_id(CARD) != card_user_id("22222222-2222-3333-4444-555555555555")


@pytest.mark.parametrize("value,secret", [
    ("bad", "test-secret"), (ticket(), "wrong"), (ticket(), ""),
    (ticket({"c": CARD, "e": 10}), "test-secret"),
    (ticket({"c": "invalid", "e": 4102444800}), "test-secret"),
    (ticket({"c": CARD, "e": True}), "test-secret"),
    (ticket({"c": CARD, "e": 4102444800, "extra": 1}), "test-secret"),
    (ticket() + "é", "test-secret"),
])
def test_invalid_ticket(value, secret):
    with pytest.raises(ValueError, match="invalid_card_ticket"):
        verify_card_ticket(value, secret, now=10)


@pytest.mark.parametrize("model,extra", [(ApiRequest, {}), (LeagueRequest, {"session_scope": "a" * 24})])
def test_credentials_are_exclusive(model, extra):
    for credentials in ({}, {"init_data": "signed", "card_ticket": ticket()}, {"card_ticket": "x" * 513}):
        with pytest.raises(ValidationError):
            model(**credentials, **extra)
    assert model(card_ticket=ticket(), **extra).card_ticket
    assert model(init_data="signed", **extra).init_data


def client(secret="test-secret"):
    from fastapi import FastAPI
    from types import SimpleNamespace
    app = FastAPI()
    app.state.settings = SimpleNamespace(admission_diagnostics_secret=secret)
    app.include_router(create_card_results_router())
    return TestClient(app)


@pytest.mark.parametrize("secret,supplied", [("", ""), ("test-secret", ""), ("test-secret", "wrong")])
def test_card_results_rejects_missing_or_wrong_secret(monkeypatch, secret, supplied):
    from diagnostic.db import attempts
    query = AsyncMock()
    monkeypatch.setattr(attempts, "list_card_results", query)
    response = client(secret).post("/api/diagnostics/card-results", json={"card_id": CARD}, headers={"x-admission-diagnostics-secret": supplied})
    assert response.status_code == 403
    query.assert_not_called()


def test_card_results_preserves_snapshot_accuracy_and_topic_order(monkeypatch):
    from diagnostic.db import attempts
    row = {"attempt_id": "attempt_123", "diagnostic_id": "ege-mathematics-1212", "mode": "quick", "completed_at": datetime(2026, 10, 3, tzinfo=timezone.utc), "correct_count": 1, "question_count": 3, "result_snapshot": {"accuracy_percent": 33}, "strong_topics": ["B", "A"], "growth_topics": ["C"]}
    query = AsyncMock(return_value=[row, row | {"result_snapshot": {}}])
    monkeypatch.setattr(attempts, "list_card_results", query)
    response = client().post("/api/diagnostics/card-results", json={"card_id": CARD}, headers={"x-admission-diagnostics-secret": "test-secret"})
    assert response.status_code == 200
    query.assert_awaited_once_with(card_user_id(CARD))
    assert [r["accuracy_percent"] for r in response.json()["results"]] == [33, 33]
    assert response.json()["results"][0]["strong_topics"] == ["B", "A"]


def test_request_user_accepts_ticket_without_telegram(monkeypatch):
    from types import SimpleNamespace
    from diagnostic.api import dependencies
    monkeypatch.setattr(dependencies, "validate_init_data", lambda *_: pytest.fail("Telegram invoked"))
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=SimpleNamespace(admission_diagnostics_secret="test-secret"))))
    assert request_user(request, ApiRequest(card_ticket=ticket())) == {"id": card_user_id(CARD)}


@pytest.mark.asyncio
async def test_card_reminder_requests_do_not_access_database(monkeypatch):
    from diagnostic.db import attempts, trainer
    async def forbidden():
        pytest.fail("card reminder accessed database")
    monkeypatch.setattr(attempts, "get_pool", forbidden)
    monkeypatch.setattr(trainer, "get_pool", forbidden)
    assert await attempts.schedule_retest_reminder(user_id=-1, attempt_id="attempt_123") == {"status": "unavailable", "reason": "notifications_disabled"}
    assert await trainer.schedule_lives_refill_reminder(-1) is None


def test_card_user_can_review_completed_attempt(monkeypatch):
    from pathlib import Path
    from types import SimpleNamespace
    from fastapi import FastAPI
    from diagnostic.api import sessions
    from diagnostic.catalog import load_catalog
    from diagnostic.school import load_school
    app = FastAPI()
    app.state.settings = SimpleNamespace(admission_diagnostics_secret="test-secret")
    school = load_school(Path(__file__).resolve().parents[1] / "school")
    app.include_router(sessions.create_router(load_catalog(school)))
    current_session = AsyncMock()
    query = AsyncMock(return_value={"status": "completed", "report_snapshot": {"review_snapshot": []}, "pdf_status": "abandoned"})
    monkeypatch.setattr(sessions, "_require_current_session", current_session)
    monkeypatch.setattr(sessions.attempts, "get_review_attempt", query)
    response = TestClient(app).post("/api/diagnostics/session/review", json={"card_ticket": ticket(), "attempt_id": "attempt_123", "session_scope": "a" * 24})
    assert response.status_code == 200
    assert response.json()["available"] is True
    query.assert_awaited_once_with("attempt_123", card_user_id(CARD))
    assert current_session.await_args.args[1:] == (card_user_id(CARD), "a" * 24)
