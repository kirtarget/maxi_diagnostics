"""Checkpoint endpoints and the checkpoint fields on /path and /today."""

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
from diagnostic.topic_checkpoint import PassedCheckpoint
from diagnostic.topic_path import TopicProgress


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_SCHOOL = ROOT / "tests/fixtures/sample-school"
APPLICATION_SECRET = "stable-installation-secret-1234567890"
SESSION_GENERATION = "1" * 32
SESSION_SCOPE = session_scope(APPLICATION_SECRET, 42, SESSION_GENERATION)

CATALOG = load_catalog(load_school(SAMPLE_SCHOOL))
DEMO = CATALOG.get("demo-math")
TOPICS = [question.topic for question in DEMO.questions]
QUESTION_IDS = [question.id for question in DEMO.questions]
VERSION = CATALOG.content_version("demo-math", APPLICATION_SECRET)

ALL_DONE = {
    topic: TopicProgress(correct_ids=frozenset({QUESTION_IDS[index]}))
    for index, topic in enumerate(TOPICS)
}


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
    from diagnostic.api.main import create_app

    monkeypatch.setattr(
        sessions, "get_session_generation", AsyncMock(return_value=SESSION_GENERATION)
    )
    settings = Settings(
        "postgresql://unused", "token", "https://app.example",
        "https://app.example", "admin", "password", None,
        application_secret=APPLICATION_SECRET,
    )
    school = load_school(SAMPLE_SCHOOL)
    return TestClient(create_app(settings, school, load_catalog(school)))


def _patch_stores(monkeypatch, *, progress, passed):
    from diagnostic.api import trainer

    monkeypatch.setattr(
        trainer.topic_progress_store, "get_progress_map",
        AsyncMock(return_value=progress),
    )
    monkeypatch.setattr(
        trainer.topic_checkpoints_store, "get_passed_map",
        AsyncMock(return_value=passed),
    )


def test_path_reports_the_unit_checkpoint(monkeypatch):
    _patch_stores(monkeypatch, progress=ALL_DONE, passed={})
    client = make_client(monkeypatch)
    payload = client.post("/api/diagnostics/path", json={
        "init_data": signed_init_data(),
        "session_scope": SESSION_SCOPE,
        "diagnostic_id": "demo-math",
        "content_version": VERSION,
    }).json()

    assert "correct" not in json.dumps(payload, ensure_ascii=False)
    assert len(payload["checkpoints"]) == 1
    node = payload["checkpoints"][0]
    assert node["unit_index"] == 0
    assert node["status"] == "available"
    assert node["topics"] == TOPICS


def test_path_checkpoint_is_locked_until_the_unit_is_done(monkeypatch):
    partial = {TOPICS[0]: TopicProgress(correct_ids=frozenset({QUESTION_IDS[0]}))}
    _patch_stores(monkeypatch, progress=partial, passed={})
    client = make_client(monkeypatch)
    payload = client.post("/api/diagnostics/path", json={
        "init_data": signed_init_data(),
        "session_scope": SESSION_SCOPE,
        "diagnostic_id": "demo-math",
        "content_version": VERSION,
    }).json()
    assert payload["checkpoints"][0]["status"] == "locked"


def test_today_signals_an_available_checkpoint(monkeypatch):
    from diagnostic.api import trainer

    _patch_stores(monkeypatch, progress=ALL_DONE, passed={})
    monkeypatch.setattr(
        trainer.topic_progress_store, "latest_completed_diagnostic",
        AsyncMock(return_value="demo-math"),
    )
    monkeypatch.setattr(
        trainer.attempts, "get_gameplay_profile", AsyncMock(return_value=None)
    )
    client = make_client(monkeypatch)
    payload = client.post("/api/diagnostics/today", json={
        "init_data": signed_init_data(),
        "session_scope": SESSION_SCOPE,
    }).json()
    assert payload["status"] == "checkpoint"
    assert payload["checkpoint_unit_index"] == 0
    assert payload["checkpoints"][0]["status"] == "available"


def test_checkpoint_start_selects_one_question_per_unit_topic(monkeypatch):
    from diagnostic.api import trainer

    _patch_stores(monkeypatch, progress=ALL_DONE, passed={})
    start = AsyncMock(return_value=(
        {
            "trainer_session_id": "C" * 32,
            "diagnostic_id": "demo-math",
            "content_version": VERSION,
            "mode": "checkpoint",
            "topic": None,
            "source_attempt_id": None,
            "question_ids": QUESTION_IDS,
            "current_index": 0,
            "revision": 1,
            "status": "active",
        },
        {"lives_remaining": 5},
    ))
    monkeypatch.setattr(trainer.trainer, "start_checkpoint_session", start)
    client = make_client(monkeypatch)
    response = client.post("/api/diagnostics/checkpoint/start", json={
        "init_data": signed_init_data(),
        "session_scope": SESSION_SCOPE,
        "diagnostic_id": "demo-math",
        "content_version": VERSION,
        "unit_index": 0,
    })
    assert response.status_code == 200
    payload = response.json()
    assert "correct" not in json.dumps(payload, ensure_ascii=False)
    assert payload["unit_index"] == 0
    assert [question["id"] for question in payload["questions"]] == QUESTION_IDS
    assert start.await_args.kwargs["selected_question_ids"] == QUESTION_IDS


def test_checkpoint_start_rejects_a_locked_unit(monkeypatch):
    partial = {TOPICS[0]: TopicProgress(correct_ids=frozenset({QUESTION_IDS[0]}))}
    _patch_stores(monkeypatch, progress=partial, passed={})
    client = make_client(monkeypatch)
    response = client.post("/api/diagnostics/checkpoint/start", json={
        "init_data": signed_init_data(),
        "session_scope": SESSION_SCOPE,
        "diagnostic_id": "demo-math",
        "content_version": VERSION,
        "unit_index": 0,
    })
    assert response.status_code == 409
    assert response.json() == {"detail": "trainer_checkpoint_unavailable"}


def test_checkpoint_record_passes_and_records_the_unit(monkeypatch):
    from diagnostic.api import trainer

    _patch_stores(monkeypatch, progress=ALL_DONE, passed={})
    monkeypatch.setattr(
        trainer.trainer, "get_session",
        AsyncMock(return_value={
            "session_id": "C" * 32,
            "diagnostic_id": "demo-math",
            "content_version": VERSION,
            "mode": "checkpoint",
            "selected_question_ids": QUESTION_IDS,
        }),
    )
    monkeypatch.setattr(
        trainer.trainer, "finish_session",
        AsyncMock(return_value={"correct_count": 5, "question_count": 5}),
    )
    record = AsyncMock(return_value=PassedCheckpoint(unit_index=0))
    monkeypatch.setattr(trainer.topic_checkpoints_store, "record_pass", record)
    client = make_client(monkeypatch)
    response = client.post("/api/diagnostics/checkpoint/record", json={
        "init_data": signed_init_data(),
        "session_scope": SESSION_SCOPE,
        "trainer_session_id": "C" * 32,
        "unit_index": 0,
        "revision": 6,
    })
    assert response.status_code == 200
    payload = response.json()
    assert payload["passed"] is True
    assert payload["mastered_count"] == 5
    assert record.await_args.kwargs["unit_index"] == 0


def test_checkpoint_record_below_threshold_does_not_record(monkeypatch):
    from diagnostic.api import trainer

    _patch_stores(monkeypatch, progress=ALL_DONE, passed={})
    monkeypatch.setattr(
        trainer.trainer, "get_session",
        AsyncMock(return_value={
            "session_id": "C" * 32,
            "diagnostic_id": "demo-math",
            "content_version": VERSION,
            "mode": "checkpoint",
            "selected_question_ids": QUESTION_IDS,
        }),
    )
    monkeypatch.setattr(
        trainer.trainer, "finish_session",
        AsyncMock(return_value={"correct_count": 2, "question_count": 5}),
    )
    record = AsyncMock()
    monkeypatch.setattr(trainer.topic_checkpoints_store, "record_pass", record)
    client = make_client(monkeypatch)
    response = client.post("/api/diagnostics/checkpoint/record", json={
        "init_data": signed_init_data(),
        "session_scope": SESSION_SCOPE,
        "trainer_session_id": "C" * 32,
        "unit_index": 0,
        "revision": 6,
    })
    assert response.status_code == 200
    assert response.json()["passed"] is False
    record.assert_not_awaited()


def test_checkpoint_record_rejects_a_unit_mismatch(monkeypatch):
    from diagnostic.api import trainer

    _patch_stores(monkeypatch, progress=ALL_DONE, passed={})
    monkeypatch.setattr(
        trainer.trainer, "get_session",
        AsyncMock(return_value={
            "session_id": "C" * 32,
            "diagnostic_id": "demo-math",
            "content_version": VERSION,
            "mode": "checkpoint",
            "selected_question_ids": [QUESTION_IDS[0]],  # not the whole unit
        }),
    )
    client = make_client(monkeypatch)
    response = client.post("/api/diagnostics/checkpoint/record", json={
        "init_data": signed_init_data(),
        "session_scope": SESSION_SCOPE,
        "trainer_session_id": "C" * 32,
        "unit_index": 0,
        "revision": 6,
    })
    assert response.status_code == 409
    assert response.json() == {"detail": "trainer_checkpoint_session_mismatch"}
