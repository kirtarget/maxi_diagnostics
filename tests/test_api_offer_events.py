import hashlib
import hmac
import json
import time
from urllib.parse import urlencode
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from diagnostic.school import load_school
from diagnostic.session_identity import session_scope
from diagnostic.settings import Settings


APPLICATION_SECRET = "stable-installation-secret-1234567890"
SESSION_GENERATION = "1" * 32
SESSION_SCOPE = session_scope(APPLICATION_SECRET, 42, SESSION_GENERATION)


def signed_init_data(*, valid: bool = True) -> str:
    pairs = {
        "auth_date": str(int(time.time())),
        "user": json.dumps({"id": 42, "first_name": "Ada"}, separators=(",", ":")),
    }
    check_string = "\n".join(f"{key}={pairs[key]}" for key in sorted(pairs))
    secret = hmac.new(b"WebAppData", b"token", hashlib.sha256).digest()
    pairs["hash"] = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    if not valid:
        pairs["hash"] = "0" * 64
    return urlencode(pairs)


class _PoolContext:
    async def __aenter__(self):
        return _Connection()

    async def __aexit__(self, *_):
        return None


class _Pool:
    def acquire(self):
        return _PoolContext()


class _Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None


class _Connection:
    def transaction(self):
        return _Transaction()


def make_client(monkeypatch):
    from diagnostic.api import sessions
    from diagnostic.api.main import create_app

    monkeypatch.setattr(
        sessions, "get_session_generation", AsyncMock(return_value=SESSION_GENERATION)
    )
    settings = Settings(
        "postgresql://unused", "token", "https://app.example",
        "https://app.example", "admin", "password", None,
        application_secret=APPLICATION_SECRET,
    )
    school = load_school()
    from diagnostic.catalog import load_catalog
    return TestClient(create_app(settings, school, load_catalog(school)))


def event_body(**overrides):
    return {
        "init_data": signed_init_data(),
        "session_scope": SESSION_SCOPE,
        "event_id": "evt_1234567890abcdef1234567890",
        "placement": "home",
        "offer_id": "exam-preparation",
        "event_type": "impression",
        **overrides,
    }


def test_invalid_init_data_is_rejected(monkeypatch):
    client = make_client(monkeypatch)
    response = client.post(
        "/api/diagnostics/offer-events",
        json=event_body(init_data=signed_init_data(valid=False)),
    )
    assert response.status_code == 403
    assert response.json() == {"detail": "invalid_init_data"}


def test_event_is_validated_and_response_is_minimal(monkeypatch):
    from diagnostic.api import offer_events

    recorder = AsyncMock(return_value=True)
    monkeypatch.setattr(offer_events.offer_events, "record_offer_event", recorder)
    monkeypatch.setattr(offer_events, "get_pool", AsyncMock(return_value=_Pool()))
    client = make_client(monkeypatch)

    response = client.post("/api/diagnostics/offer-events", json=event_body())

    assert response.status_code == 200
    assert response.json() == {"ok": True, "recorded": True}
    assert "init_data" not in response.text
    assert "user_id" not in response.text
    assert "url" not in response.text
    assert recorder.await_args.kwargs["offer_id"] == "exam-preparation"
    assert recorder.await_args.kwargs["placement"] == "home"
    assert recorder.await_args.kwargs["event_type"] == "impression"


def test_unknown_offer_and_placement_are_rejected(monkeypatch):
    client = make_client(monkeypatch)
    assert client.post(
        "/api/diagnostics/offer-events", json=event_body(offer_id="unknown")
    ).status_code == 422
    assert client.post(
        "/api/diagnostics/offer-events", json=event_body(placement="unknown")
    ).status_code == 422


def test_conflict_and_rate_limit_are_safe_errors(monkeypatch):
    from diagnostic.api import offer_events

    recorder = AsyncMock(side_effect=[ValueError("offer_event_conflict"), ValueError("offer_event_rate_limited")])
    monkeypatch.setattr(offer_events.offer_events, "record_offer_event", recorder)
    monkeypatch.setattr(offer_events, "get_pool", AsyncMock(return_value=_Pool()))
    client = make_client(monkeypatch)

    first = client.post("/api/diagnostics/offer-events", json=event_body())
    second = client.post("/api/diagnostics/offer-events", json=event_body(event_id="evt_1234567890abcdef1234567891"))
    assert first.status_code == 409
    assert first.json() == {"detail": "offer_event_conflict"}
    assert second.status_code == 429
    assert second.json() == {"detail": "offer_event_rate_limited"}


def test_extra_fields_are_rejected(monkeypatch):
    client = make_client(monkeypatch)
    response = client.post(
        "/api/diagnostics/offer-events", json=event_body(secret="nope")
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "request_invalid"
