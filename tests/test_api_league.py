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


def league_body(**overrides):
    return {
        "init_data": signed_init_data(),
        "session_scope": SESSION_SCOPE,
        **overrides,
    }


class _PoolContext:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *_):
        return None


class _Pool:
    def acquire(self):
        return _PoolContext()


def test_invalid_init_data_is_rejected(monkeypatch):
    client = make_client(monkeypatch)
    response = client.post(
        "/api/diagnostics/league", json=league_body(init_data=signed_init_data(valid=False))
    )
    assert response.status_code == 403
    assert response.json() == {"detail": "invalid_init_data"}


def test_stale_session_scope_is_rejected(monkeypatch):
    from diagnostic.api import sessions

    client = make_client(monkeypatch)
    monkeypatch.setattr(sessions, "get_session_generation", AsyncMock(return_value="2" * 32))
    response = client.post("/api/diagnostics/league", json=league_body())
    assert response.status_code == 409
    assert response.json() == {"detail": "session_expired"}


def test_league_response_is_server_owned_and_privacy_safe(monkeypatch):
    from diagnostic.api import league

    expected = {
        "ok": True,
        "week_key": "2026-08-24",
        "week_start": "2026-08-24",
        "week_end": "2026-08-30",
        "status": "forming",
        "participant_count": 2,
        "rows": [],
        "me": {"rank": 1, "xp_week": 20},
    }
    getter = AsyncMock(return_value=expected)
    monkeypatch.setattr(league.league, "get_weekly_league", getter)
    monkeypatch.setattr(league, "get_pool", AsyncMock(return_value=_Pool()))
    client = make_client(monkeypatch)
    response = client.post("/api/diagnostics/league", json=league_body())

    assert response.status_code == 200
    assert response.json() == expected
    assert "user_id" not in response.text
    assert "first_name" not in response.text
    assert getter.await_args.kwargs["user_id"] == 42


def test_extra_fields_are_rejected(monkeypatch):
    client = make_client(monkeypatch)
    response = client.post("/api/diagnostics/league", json=league_body(secret="nope"))
    assert response.status_code == 422
    assert response.json()["detail"] == "request_invalid"
