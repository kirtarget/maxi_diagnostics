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


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_SCHOOL = ROOT / "tests/fixtures/sample-school"
APPLICATION_SECRET = "stable-installation-secret-1234567890"
SESSION_GENERATION = "1" * 32
SESSION_SCOPE = session_scope(APPLICATION_SECRET, 42, SESSION_GENERATION)


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


def stored_plan(**overrides) -> dict:
    catalog = load_catalog(load_school(SAMPLE_SCHOOL))
    plan = {
        "plan_date": "2026-09-02",
        "diagnostic_id": "demo-math",
        "content_version": catalog.content_version("demo-math", APPLICATION_SECRET),
        "source_attempt_id": "attempt_1",
        "question_ids": ["q3", "q1"],
        "reasons": {"q3": "mistake_review", "q1": "growth_topic"},
        "completed_question_ids": ["q3"],
        "total": 2,
        "completed": 1,
    }
    return plan | overrides


def plan_body() -> dict:
    return {"init_data": signed_init_data(), "session_scope": SESSION_SCOPE}


def test_daily_plan_returns_public_questions_with_reasons(monkeypatch):
    from diagnostic.api import trainer

    monkeypatch.setattr(
        trainer, "ensure_today_plan", AsyncMock(return_value=stored_plan())
    )
    client = make_client(monkeypatch)

    response = client.post("/api/diagnostics/daily-plan", json=plan_body())

    assert response.status_code == 200
    payload = response.json()
    assert "correct" not in json.dumps(payload, ensure_ascii=False)
    assert payload["status"] == "ready"
    assert payload["subject"] == "Математика"
    assert payload["total"] == 2
    assert payload["completed"] == 1
    assert payload["questions"] == [
        {"question_id": "q3", "topic": "Соответствия", "reason": "mistake_review", "completed": True},
        {"question_id": "q1", "topic": "Вычисления", "reason": "growth_topic", "completed": False},
    ]


def test_daily_plan_reports_done_when_every_question_is_answered(monkeypatch):
    from diagnostic.api import trainer

    monkeypatch.setattr(
        trainer, "ensure_today_plan",
        AsyncMock(return_value=stored_plan(completed_question_ids=["q3", "q1"], completed=2)),
    )
    client = make_client(monkeypatch)

    assert client.post("/api/diagnostics/daily-plan", json=plan_body()).json()["status"] == "done"


def test_daily_plan_reports_no_diagnostic_without_a_completed_attempt(monkeypatch):
    from diagnostic.api import trainer

    monkeypatch.setattr(trainer, "ensure_today_plan", AsyncMock(return_value=None))
    client = make_client(monkeypatch)

    payload = client.post("/api/diagnostics/daily-plan", json=plan_body()).json()
    assert payload["status"] == "no_diagnostic"
    assert payload["questions"] == []
    assert payload["total"] == 0


def test_daily_plan_requires_the_current_session_scope(monkeypatch):
    from diagnostic.api import sessions, trainer

    monkeypatch.setattr(trainer, "ensure_today_plan", AsyncMock(return_value=stored_plan()))
    client = make_client(monkeypatch)
    monkeypatch.setattr(
        sessions, "get_session_generation", AsyncMock(return_value="2" * 32)
    )

    response = client.post("/api/diagnostics/daily-plan", json=plan_body())
    assert response.status_code == 409
    assert response.json() == {"detail": "session_expired"}


def test_trainer_plan_mode_starts_the_stored_plan_in_order(monkeypatch):
    from diagnostic.api import trainer

    monkeypatch.setattr(trainer, "ensure_today_plan", AsyncMock(return_value=stored_plan()))
    start_session = AsyncMock(return_value=(
        {
            "trainer_session_id": "A" * 32,
            "diagnostic_id": "demo-math",
            "content_version": "a" * 64,
            "mode": "plan",
            "question_ids": ["q3", "q1"],
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
        "mode": "plan",
    })

    assert response.status_code == 200
    payload = response.json()
    assert "correct" not in json.dumps(payload, ensure_ascii=False)
    assert [question["id"] for question in payload["questions"]] == ["q3", "q1"]
    assert payload["plan"] == {
        "plan_date": "2026-09-02", "total": 2, "completed": 1,
        "reasons": {"q3": "mistake_review", "q1": "growth_topic"},
    }
    assert start_session.await_args.kwargs["selected_question_ids"] == ["q3", "q1"]
    assert start_session.await_args.kwargs["mode"] == "plan"
    assert start_session.await_args.kwargs["source_attempt_id"] is None


def test_trainer_plan_mode_reports_an_unavailable_plan(monkeypatch):
    from diagnostic.api import trainer

    monkeypatch.setattr(trainer, "ensure_today_plan", AsyncMock(return_value=None))
    client = make_client(monkeypatch)

    response = client.post("/api/diagnostics/trainer/start", json={
        "init_data": signed_init_data(),
        "session_scope": SESSION_SCOPE,
        "diagnostic_id": "demo-math",
        "count": 5,
        "mode": "plan",
    })
    assert response.status_code == 409
    assert response.json() == {"detail": "trainer_plan_unavailable"}


def test_trainer_plan_mode_rejects_a_plan_for_another_diagnostic(monkeypatch):
    from diagnostic.api import trainer

    monkeypatch.setattr(
        trainer, "ensure_today_plan",
        AsyncMock(return_value=stored_plan(diagnostic_id="demo-other")),
    )
    client = make_client(monkeypatch)

    response = client.post("/api/diagnostics/trainer/start", json={
        "init_data": signed_init_data(),
        "session_scope": SESSION_SCOPE,
        "diagnostic_id": "demo-math",
        "count": 5,
        "mode": "plan",
    })
    assert response.status_code == 409
    assert response.json() == {"detail": "trainer_plan_conflict"}


def test_trainer_plan_mode_rejects_a_plan_built_on_older_content(monkeypatch):
    from diagnostic.api import trainer

    monkeypatch.setattr(
        trainer, "ensure_today_plan",
        AsyncMock(return_value=stored_plan(content_version="b" * 64)),
    )
    client = make_client(monkeypatch)

    response = client.post("/api/diagnostics/trainer/start", json={
        "init_data": signed_init_data(),
        "session_scope": SESSION_SCOPE,
        "diagnostic_id": "demo-math",
        "count": 5,
        "mode": "plan",
    })
    assert response.status_code == 409
    assert response.json() == {"detail": "trainer_content_changed"}


def test_bootstrap_carries_the_daily_plan_summary(monkeypatch):
    from diagnostic.api import sessions

    monkeypatch.setattr(sessions.attempts, "mark_opened", AsyncMock(return_value=False))
    monkeypatch.setattr(sessions, "get_resumable_attempt", AsyncMock(return_value=None))
    monkeypatch.setattr(sessions, "list_completed_attempts", AsyncMock(return_value=[]))
    monkeypatch.setattr(sessions, "get_latest_attempt_id", AsyncMock(return_value=None))
    monkeypatch.setattr(sessions, "get_progress_profile", AsyncMock(return_value=None))
    monkeypatch.setattr(sessions, "get_gameplay_profile", AsyncMock(return_value=None))
    monkeypatch.setattr(
        sessions, "get_or_create_session_generation",
        AsyncMock(return_value=SESSION_GENERATION),
    )
    monkeypatch.setattr(sessions, "ensure_today_plan", AsyncMock(return_value=stored_plan()))
    client = make_client(monkeypatch)

    payload = client.post(
        "/api/diagnostics/bootstrap", json={"init_data": signed_init_data()}
    ).json()

    assert payload["daily_plan"] == {
        "plan_date": "2026-09-02",
        "diagnostic_id": "demo-math",
        "subject": "Математика",
        "exam": "demo",
        "total": 2,
        "completed": 1,
        "status": "ready",
    }


def test_bootstrap_reports_no_plan_before_the_first_completed_diagnostic(monkeypatch):
    from diagnostic.api import sessions

    monkeypatch.setattr(sessions.attempts, "mark_opened", AsyncMock(return_value=False))
    monkeypatch.setattr(sessions, "get_resumable_attempt", AsyncMock(return_value=None))
    monkeypatch.setattr(sessions, "list_completed_attempts", AsyncMock(return_value=[]))
    monkeypatch.setattr(sessions, "get_latest_attempt_id", AsyncMock(return_value=None))
    monkeypatch.setattr(sessions, "get_progress_profile", AsyncMock(return_value=None))
    monkeypatch.setattr(sessions, "get_gameplay_profile", AsyncMock(return_value=None))
    monkeypatch.setattr(
        sessions, "get_or_create_session_generation",
        AsyncMock(return_value=SESSION_GENERATION),
    )
    monkeypatch.setattr(sessions, "ensure_today_plan", AsyncMock(return_value=None))
    client = make_client(monkeypatch)

    payload = client.post(
        "/api/diagnostics/bootstrap", json={"init_data": signed_init_data()}
    ).json()
    assert payload["daily_plan"]["status"] == "no_diagnostic"
    assert payload["daily_plan"]["total"] == 0
