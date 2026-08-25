import hashlib
import hmac
import json
import time
from pathlib import Path
from urllib.parse import urlencode
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from diagnostic.catalog import load_catalog
from diagnostic.school import load_school
from diagnostic.session_identity import session_scope
from diagnostic.settings import Settings


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_SCHOOL = ROOT / "tests/fixtures/sample-school"
APPLICATION_SECRET = "stable-installation-secret-1234567890"
SESSION_GENERATION = "1" * 32
SESSION_SCOPE = session_scope(APPLICATION_SECRET, 42, SESSION_GENERATION)


def signed_init_data(user_id: int = 42, *, valid: bool = True) -> str:
    pairs = {
        "auth_date": str(int(time.time())),
        "user": json.dumps({"id": user_id, "first_name": "Ada"}, separators=(",", ":")),
    }
    check_string = "\n".join(f"{key}={pairs[key]}" for key in sorted(pairs))
    secret = hmac.new(b"WebAppData", b"token", hashlib.sha256).digest()
    pairs["hash"] = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    if not valid:
        pairs["hash"] = "0" * 64
    return urlencode(pairs)


def make_client(monkeypatch, *, generation: str = SESSION_GENERATION) -> TestClient:
    from diagnostic.api import sessions
    from diagnostic.api.main import create_app

    monkeypatch.setattr(
        sessions, "get_session_generation", AsyncMock(return_value=generation)
    )
    settings = Settings(
        "postgresql://unused", "token", "https://app.example",
        "https://app.example", "admin", "password", None,
        application_secret=APPLICATION_SECRET,
    )
    school = load_school(SAMPLE_SCHOOL)
    return TestClient(create_app(settings, school, load_catalog(school)))


def start_body(**overrides) -> dict:
    body = {
        "init_data": signed_init_data(),
        "session_scope": SESSION_SCOPE,
        "diagnostic_id": "demo-math",
        "count": 1,
        "mode": "normal",
    }
    return body | overrides


def answer_body(**overrides) -> dict:
    body = {
        "init_data": signed_init_data(),
        "session_scope": SESSION_SCOPE,
        "trainer_session_id": "A" * 32,
        "question_id": "q1",
        "answer": "2",
        "revision": 1,
    }
    return body | overrides


def finish_body(**overrides) -> dict:
    body = {
        "init_data": signed_init_data(),
        "session_scope": SESSION_SCOPE,
        "trainer_session_id": "A" * 32,
        "revision": 2,
    }
    return body | overrides


def test_invalid_telegram_signature_is_rejected_before_db(monkeypatch):
    client = make_client(monkeypatch)
    response = client.post("/api/diagnostics/trainer/start", json=start_body(init_data=signed_init_data(valid=False)))

    assert response.status_code == 403
    assert response.json() == {"detail": "invalid_init_data"}


def test_stale_session_scope_is_rejected(monkeypatch):
    client = make_client(monkeypatch, generation="2" * 32)
    response = client.post("/api/diagnostics/trainer/start", json=start_body())

    assert response.status_code == 409
    assert response.json() == {"detail": "session_expired"}


def test_start_uses_authenticated_user_and_returns_public_questions(monkeypatch):
    from diagnostic.api import trainer

    start_session = AsyncMock(return_value=(
        {
            "trainer_session_id": "A" * 32,
            "diagnostic_id": "demo-math",
            "content_version": "a" * 64,
            "mode": "normal",
            "question_ids": ["q1"],
            "current_index": 0,
            "revision": 1,
            "status": "active",
        },
        {"lives_remaining": 5},
    ))
    monkeypatch.setattr(trainer.trainer, "start_session", start_session)
    client = make_client(monkeypatch)

    response = client.post("/api/diagnostics/trainer/start", json=start_body())

    assert response.status_code == 200
    payload = response.json()
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "correct" not in serialized
    assert "explanation" not in serialized
    assert "learning_material" not in serialized
    assert payload["questions"][0]["id"] == "q1"
    assert payload["lives_remaining"] == 5
    assert start_session.await_args.kwargs["user_id"] == 42


def test_mistakes_mode_is_explicitly_unavailable(monkeypatch):
    client = make_client(monkeypatch)
    response = client.post(
        "/api/diagnostics/trainer/start", json=start_body(mode="mistakes")
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "trainer_mode_not_available"}


@pytest.mark.parametrize(
    ("overrides", "detail"),
    [
        ({"count": 0}, "request_invalid"),
        ({"topic": "missing-topic"}, "trainer_not_enough_questions"),
        ({"diagnostic_id": "missing-diagnostic"}, "diagnostic_not_found"),
    ],
)
def test_start_rejects_invalid_count_topic_or_diagnostic(monkeypatch, overrides, detail):
    client = make_client(monkeypatch)
    response = client.post(
        "/api/diagnostics/trainer/start", json=start_body(**overrides)
    )

    assert response.status_code == 422
    assert response.json()["detail"] == detail


def test_answer_rejects_unknown_question(monkeypatch):
    from diagnostic.api import trainer

    monkeypatch.setattr(
        trainer.trainer, "get_session", AsyncMock(return_value={
            "diagnostic_id": "demo-math", "content_version": load_catalog(load_school(SAMPLE_SCHOOL)).content_version("demo-math", APPLICATION_SECRET),
        })
    )
    client = make_client(monkeypatch)
    response = client.post(
        "/api/diagnostics/trainer/answer", json=answer_body(question_id="missing")
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "trainer_question_not_found"}


def test_answer_returns_feedback_only_after_submission(monkeypatch):
    from diagnostic.api import trainer

    catalog = load_catalog(load_school(SAMPLE_SCHOOL))
    monkeypatch.setattr(trainer.trainer, "get_session", AsyncMock(return_value={
        "diagnostic_id": "demo-math",
        "content_version": catalog.content_version("demo-math", APPLICATION_SECRET),
    }))
    submit = AsyncMock(return_value={
        "ok": True, "question_id": "q1", "is_correct": True,
        "correct_answer": "4", "explanation": "Сложите два и два: получится четыре.",
    })
    monkeypatch.setattr(trainer.trainer, "answer_question", submit)
    client = make_client(monkeypatch)

    response = client.post("/api/diagnostics/trainer/answer", json=answer_body())

    assert response.status_code == 200
    assert response.json()["correct_answer"] == "4"
    assert response.json()["explanation"]
    assert submit.await_args.kwargs["public_feedback"]["correct_answer"] == "4"


@pytest.mark.parametrize("error", ["trainer_answer_conflict", "trainer_revision_stale"])
def test_answer_conflicts_map_to_safe_http_errors(monkeypatch, error):
    from diagnostic.api import trainer

    catalog = load_catalog(load_school(SAMPLE_SCHOOL))
    monkeypatch.setattr(trainer.trainer, "get_session", AsyncMock(return_value={
        "diagnostic_id": "demo-math",
        "content_version": catalog.content_version("demo-math", APPLICATION_SECRET),
    }))
    monkeypatch.setattr(
        trainer.trainer, "answer_question", AsyncMock(side_effect=ValueError(error))
    )
    client = make_client(monkeypatch)

    response = client.post("/api/diagnostics/trainer/answer", json=answer_body())

    assert response.status_code == 409
    assert response.json() == {"detail": error}


def test_zero_lives_maps_to_conflict(monkeypatch):
    from diagnostic.api import trainer

    catalog = load_catalog(load_school(SAMPLE_SCHOOL))
    monkeypatch.setattr(trainer.trainer, "get_session", AsyncMock(return_value={
        "diagnostic_id": "demo-math",
        "content_version": catalog.content_version("demo-math", APPLICATION_SECRET),
    }))
    monkeypatch.setattr(
        trainer.trainer, "answer_question", AsyncMock(side_effect=ValueError("trainer_no_lives"))
    )
    client = make_client(monkeypatch)

    response = client.post("/api/diagnostics/trainer/answer", json=answer_body(answer="1"))

    assert response.status_code == 409
    assert response.json() == {"detail": "trainer_no_lives"}


def test_answer_session_isolation_uses_authenticated_owner(monkeypatch):
    from diagnostic.api import trainer

    get_session = AsyncMock(return_value=None)
    monkeypatch.setattr(trainer.trainer, "get_session", get_session)
    client = make_client(monkeypatch)

    response = client.post("/api/diagnostics/trainer/answer", json=answer_body())

    assert response.status_code == 404
    assert response.json() == {"detail": "trainer_session_not_found"}
    assert get_session.await_args.args == ("A" * 32, 42)


@pytest.mark.parametrize("error", ["trainer_session_incomplete", "trainer_revision_stale"])
def test_finish_incomplete_or_stale_revision_maps_to_conflict(monkeypatch, error):
    from diagnostic.api import trainer

    monkeypatch.setattr(
        trainer.trainer, "finish_session", AsyncMock(side_effect=ValueError(error))
    )
    client = make_client(monkeypatch)

    response = client.post("/api/diagnostics/trainer/finish", json=finish_body())

    assert response.status_code == 409
    assert response.json() == {"detail": error}
