import hashlib
import hmac
import json
import time
from pathlib import Path
from urllib.parse import urlencode
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from diagnostic.catalog import load_catalog
from diagnostic.school import load_school
from diagnostic.session_identity import session_scope
from diagnostic.settings import Settings
from diagnostic.topic_path import TopicProgress


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_SCHOOL = ROOT / "tests/fixtures/sample-school"
APPLICATION_SECRET = "stable-installation-secret-1234567890"
SESSION_GENERATION = "1" * 32
SESSION_SCOPE = session_scope(APPLICATION_SECRET, 42, SESSION_GENERATION)

CATALOG = load_catalog(load_school(SAMPLE_SCHOOL))
DEMO = CATALOG.get("demo-math")
TOPICS = [question.topic for question in DEMO.questions]  # five single-question topics
QUESTION_IDS = [question.id for question in DEMO.questions]
VERSION = CATALOG.content_version("demo-math", APPLICATION_SECRET)


def signed_init_data(user_id: int = 42) -> str:
    pairs = {
        "auth_date": str(int(time.time())),
        "user": json.dumps({"id": user_id, "first_name": "Ada"}, separators=(",", ":")),
    }
    check_string = "\n".join(f"{key}={pairs[key]}" for key in sorted(pairs))
    secret = hmac.new(b"WebAppData", b"token", hashlib.sha256).digest()
    pairs["hash"] = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode(pairs)


def make_client(monkeypatch) -> TestClient:
    from diagnostic.api import sessions
    from diagnostic.api import trainer
    from diagnostic.api.main import create_app

    monkeypatch.setattr(
        sessions, "get_session_generation", AsyncMock(return_value=SESSION_GENERATION)
    )
    monkeypatch.setattr(
        trainer.trainer, "get_resumable_session", AsyncMock(return_value=None)
    )
    settings = Settings(
        "postgresql://unused", "token", "https://app.example",
        "https://app.example", "admin", "password", None,
        application_secret=APPLICATION_SECRET,
    )
    school = load_school(SAMPLE_SCHOOL)
    return TestClient(create_app(settings, school, load_catalog(school)))


def test_path_endpoint_derives_statuses_from_progress(monkeypatch):
    from diagnostic.api import trainer

    # First topic mastered; the rest untouched.
    progress = {TOPICS[0]: TopicProgress(correct_ids=frozenset({QUESTION_IDS[0]}))}
    monkeypatch.setattr(
        trainer.topic_progress_store, "get_progress_map",
        AsyncMock(return_value=progress),
    )
    client = make_client(monkeypatch)

    response = client.post("/api/diagnostics/path", json={
        "init_data": signed_init_data(),
        "session_scope": SESSION_SCOPE,
        "diagnostic_id": "demo-math",
        "content_version": VERSION,
    })

    assert response.status_code == 200
    payload = response.json()
    assert "correct" not in json.dumps(payload, ensure_ascii=False)
    statuses = [(node["topic"], node["status"]) for node in payload["topics"]]
    assert statuses[0] == (TOPICS[0], "done")
    assert statuses[1] == (TOPICS[1], "current")
    assert all(status == "locked" for _, status in statuses[2:])
    assert payload["current_topic"] == TOPICS[1]
    assert payload["done_count"] == 1
    assert payload["total_count"] == 5


def test_path_endpoint_rejects_a_stale_content_version(monkeypatch):
    from diagnostic.api import trainer

    monkeypatch.setattr(
        trainer.topic_progress_store, "get_progress_map", AsyncMock(return_value={})
    )
    client = make_client(monkeypatch)

    response = client.post("/api/diagnostics/path", json={
        "init_data": signed_init_data(),
        "session_scope": SESSION_SCOPE,
        "diagnostic_id": "demo-math",
        "content_version": "0" * 64,
    })
    assert response.status_code == 409
    assert response.json() == {"detail": "trainer_content_changed"}


def test_today_endpoint_describes_the_current_topic(monkeypatch):
    from diagnostic.api import trainer

    monkeypatch.setattr(
        trainer.topic_progress_store, "latest_completed_diagnostic",
        AsyncMock(return_value="demo-math"),
    )
    monkeypatch.setattr(
        trainer.topic_progress_store, "get_progress_map", AsyncMock(return_value={})
    )
    monkeypatch.setattr(
        trainer.attempts, "get_gameplay_profile", AsyncMock(return_value=None)
    )
    client = make_client(monkeypatch)

    payload = client.post("/api/diagnostics/today", json={
        "init_data": signed_init_data(),
        "session_scope": SESSION_SCOPE,
    }).json()

    assert "correct" not in json.dumps(payload, ensure_ascii=False)
    assert payload["status"] == "ready"
    assert payload["diagnostic_id"] == "demo-math"
    assert payload["topic"] == TOPICS[0]
    assert payload["size"] == 1  # the current topic has one question
    assert payload["estimated_minutes"] == 1
    assert payload["streak_days"] == 0
    assert payload["daily_goal"]["target"] == 1
    assert len(payload["path"]) == 5


def test_today_endpoint_reports_no_diagnostic(monkeypatch):
    from diagnostic.api import trainer

    monkeypatch.setattr(
        trainer.topic_progress_store, "latest_completed_diagnostic",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        trainer.attempts, "get_gameplay_profile", AsyncMock(return_value=None)
    )
    client = make_client(monkeypatch)

    payload = client.post("/api/diagnostics/today", json={
        "init_data": signed_init_data(),
        "session_scope": SESSION_SCOPE,
    }).json()
    assert payload["status"] == "no_diagnostic"
    assert payload["size"] == 0
    assert payload["path"] == []


def test_today_start_mode_selects_the_current_topic(monkeypatch):
    from diagnostic.api import trainer

    monkeypatch.setattr(
        trainer.topic_progress_store, "get_progress_map", AsyncMock(return_value={})
    )
    start_session = AsyncMock(return_value=(
        {
            "trainer_session_id": "T" * 32,
            "diagnostic_id": "demo-math",
            "content_version": VERSION,
            "mode": "today",
            "topic": TOPICS[0],
            "question_ids": [QUESTION_IDS[0]],
            "current_index": 0,
            "revision": 1,
            "status": "active",
        },
        {"lives_remaining": 5},
    ))
    monkeypatch.setattr(trainer.trainer, "start_session", start_session)
    client = make_client(monkeypatch)

    response = client.post("/api/diagnostics/trainer/start", json={
        "init_data": signed_init_data(),
        "session_scope": SESSION_SCOPE,
        "diagnostic_id": "demo-math",
        "count": 5,
        "mode": "today",
    })

    assert response.status_code == 200
    payload = response.json()
    assert "correct" not in json.dumps(payload, ensure_ascii=False)
    assert [question["id"] for question in payload["questions"]] == [QUESTION_IDS[0]]
    assert start_session.await_args.kwargs["mode"] == "today"
    assert start_session.await_args.kwargs["topic"] == TOPICS[0]
    assert start_session.await_args.kwargs["selected_question_ids"] == [QUESTION_IDS[0]]


def test_today_start_mode_reports_a_complete_path(monkeypatch):
    from diagnostic.api import trainer

    everything = {
        topic: TopicProgress(correct_ids=frozenset({QUESTION_IDS[index]}))
        for index, topic in enumerate(TOPICS)
    }
    monkeypatch.setattr(
        trainer.topic_progress_store, "get_progress_map",
        AsyncMock(return_value=everything),
    )
    client = make_client(monkeypatch)

    response = client.post("/api/diagnostics/trainer/start", json={
        "init_data": signed_init_data(),
        "session_scope": SESSION_SCOPE,
        "diagnostic_id": "demo-math",
        "count": 5,
        "mode": "today",
    })
    assert response.status_code == 409
    assert response.json() == {"detail": "trainer_path_complete"}
