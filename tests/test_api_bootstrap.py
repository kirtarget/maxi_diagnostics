import hashlib
import hmac
import json
import time
from pathlib import Path
from unittest.mock import AsyncMock
from urllib.parse import urlencode

from fastapi.testclient import TestClient

from diagnostic.catalog import load_catalog
from diagnostic.school import load_school
from diagnostic.settings import Settings


ROOT = Path(__file__).resolve().parents[1]


def signed_init_data() -> str:
    pairs = {
        "auth_date": str(int(time.time())),
        "user": json.dumps({"id": 42, "first_name": "Ada"}, separators=(",", ":")),
    }
    check_string = "\n".join(f"{key}={pairs[key]}" for key in sorted(pairs))
    secret = hmac.new(b"WebAppData", b"token", hashlib.sha256).digest()
    pairs["hash"] = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode(pairs)


def make_client(monkeypatch) -> TestClient:
    from diagnostic.api.main import create_app
    from diagnostic.api import sessions

    async def mark_opened(_: int) -> None:
        return None

    async def get_resumable_attempt(_: int):
        return None

    async def list_completed_attempts(_: int):
        return []

    async def get_latest_attempt_id(_: int):
        return None

    async def get_progress_profile(_: int):
        return None

    monkeypatch.setattr(sessions.attempts, "mark_opened", mark_opened)
    monkeypatch.setattr(sessions, "get_resumable_attempt", get_resumable_attempt)
    monkeypatch.setattr(sessions, "list_completed_attempts", list_completed_attempts)
    monkeypatch.setattr(sessions, "get_latest_attempt_id", get_latest_attempt_id)
    monkeypatch.setattr(sessions, "get_progress_profile", get_progress_profile)
    monkeypatch.setattr(
        sessions, "get_or_create_session_generation", AsyncMock(return_value="1" * 32)
    )
    settings = Settings("postgresql://unused", "token", "https://app.example", "https://app.example", "admin", "password", None)
    school = load_school(ROOT / "school")
    return TestClient(create_app(settings, school, load_catalog(school)))


def test_bootstrap_returns_brand_and_sanitized_catalog(monkeypatch):
    from diagnostic.api import sessions

    client = make_client(monkeypatch)
    monkeypatch.setattr(
        sessions, "get_latest_attempt_id", AsyncMock(return_value="attempt-latest")
    )
    configured_school = load_school(ROOT / "school")

    response = client.post("/api/diagnostics/bootstrap", json={"init_data": signed_init_data()})

    assert response.status_code == 200
    body = response.json()
    assert body["latest_attempt_id"] == "attempt-latest"
    assert body["progress_profile"] == {
        "completion_count": 0,
        "achievement_keys": [],
    }
    assert body["gameplay_profile"] == {
        "xp_total": 0,
        "level": 1,
        "level_progress": 0,
        "streak_days": 0,
        "lives_remaining": 5,
        "daily_goal": {
            "date": None,
            "target": 1,
            "progress": 0,
            "complete": False,
        },
        "quest": None,
    }
    assert set(body["gameplay_profile"]) == {
        "xp_total", "level", "level_progress", "streak_days",
        "lives_remaining", "daily_goal", "quest",
    }
    assert body["school"]["brand"]["name"] == configured_school.brand.name
    assert '"correct"' not in json.dumps(body["diagnostics"], ensure_ascii=False)


def test_bootstrap_returns_only_public_progress_profile_fields(monkeypatch):
    from diagnostic.api import sessions

    client = make_client(monkeypatch)
    monkeypatch.setattr(
        sessions,
        "get_progress_profile",
        AsyncMock(return_value={
            "user_id": 42,
            "completion_count": 3,
            "achievement_keys": ["first_diagnostic_completed", 99],
            "updated_at": "private",
        }),
    )

    response = client.post("/api/diagnostics/bootstrap", json={"init_data": signed_init_data()})

    assert response.status_code == 200
    assert response.json()["progress_profile"] == {
        "completion_count": 3,
        "achievement_keys": ["first_diagnostic_completed"],
    }
    assert "user_id" not in response.json()["progress_profile"]


def test_bootstrap_rejects_invalid_telegram_signature(monkeypatch):
    client = make_client(monkeypatch)

    response = client.post("/api/diagnostics/bootstrap", json={"init_data": "auth_date=1&hash=bad"})

    assert response.status_code == 403


def test_healthz_reports_database_readiness(monkeypatch):
    from diagnostic.api import main

    ready = AsyncMock(side_effect=[False, True])
    monkeypatch.setattr(main, "database_ready", ready)
    client = make_client(monkeypatch)

    unavailable = client.get("/healthz")
    healthy = client.get("/healthz")

    assert unavailable.status_code == 503
    assert unavailable.json() == {"ok": False}
    assert healthy.status_code == 200
    assert healthy.json() == {"ok": True}


def test_bootstrap_retires_stale_content_attempt_and_hides_it(monkeypatch):
    from diagnostic.api import sessions

    stale = {
        "attempt_id": "attempt-old", "user_id": 42, "diagnostic_id": "demo-math",
        "content_version": "0" * 64, "status": "in_progress",
    }
    retired = AsyncMock(return_value=True)
    client = make_client(monkeypatch)
    monkeypatch.setattr(sessions, "get_resumable_attempt", AsyncMock(return_value=stale))
    monkeypatch.setattr(sessions.attempts, "supersede_stale_attempt", retired)

    response = client.post(
        "/api/diagnostics/bootstrap", json={"init_data": signed_init_data()}
    )

    assert response.status_code == 200
    assert response.json()["attempt"] is None
    retired.assert_awaited_once_with("attempt-old", 42)
