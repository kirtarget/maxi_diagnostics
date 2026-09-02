from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from diagnostic.catalog import load_catalog
from diagnostic.school import load_school
from diagnostic.settings import Settings


ROOT = Path(__file__).resolve().parents[1]
ADMIN_AUTH = ("admin-user", "admin-password")


def make_client(monkeypatch) -> TestClient:
    from diagnostic.admin import router
    from diagnostic.api.main import create_app

    monkeypatch.setattr(router.repository, "get_summary", AsyncMock(return_value={"attempts": 3, "completed": 2, "pending_pdfs": 1, "due_notifications": 1}))
    monkeypatch.setattr(router.repository, "list_attempts", AsyncMock(return_value=(0, [])))
    monkeypatch.setattr(router.repository, "list_delivery_issues", AsyncMock(return_value=(0, [])))
    monkeypatch.setattr(router.repository, "list_notification_issues", AsyncMock(return_value=(0, [])))
    monkeypatch.setattr(router.repository, "list_messages", AsyncMock(return_value=[]))
    monkeypatch.setattr(router.repository, "update_message", AsyncMock(return_value=None))
    monkeypatch.setattr(router.repository, "delete_diagnostic_user", AsyncMock(return_value={"notifications": 0, "attempts": 0, "engagements": 0}))
    settings = Settings("postgresql://unused", "123456:test-token", "https://app.example", "https://app.example", ADMIN_AUTH[0], ADMIN_AUTH[1], None)
    school = load_school(ROOT / "school")
    return TestClient(create_app(settings, school, load_catalog(school)))


def test_summary_is_diagnostic_only(monkeypatch):
    from diagnostic.admin import router

    client = make_client(monkeypatch)
    response = client.get("/api/admin/diagnostics/summary", auth=ADMIN_AUTH)

    assert response.status_code == 200
    assert response.json() == {"attempts": 3, "completed": 2, "pending_pdfs": 1, "due_notifications": 1}
    router.repository.get_summary.assert_awaited_once()


def test_attempt_api_allowlists_fields_and_omits_sensitive_payloads(monkeypatch):
    from diagnostic.admin import router

    client = make_client(monkeypatch)
    router.repository.list_attempts.return_value = (
        1,
        [{
            "attempt_id": "attempt_123", "user_id": 42, "diagnostic_id": "demo-math",
            "exam": "demo", "subject": "Математика", "mode": "quick", "status": "completed",
            "question_index": 2, "question_count": 2, "correct_count": 2, "score": 100,
            "max_score": 100, "score_unit": "accuracy_percent", "pdf_status": "sent",
            "pdf_attempts": 1, "updated_at": None, "completed_at": None,
            "answers": {"q1": "secret"}, "telegram_username": "private", "first_name": "Private",
            "result_snapshot": {"answers": "secret"}, "pdf_last_error": "token=secret",
            "initData": "secret", "url": "https://secret.example/token",
        }],
    )

    response = client.get("/api/admin/diagnostics/attempts?limit=25&offset=5", auth=ADMIN_AUTH)
    encoded = json.dumps(response.json(), ensure_ascii=False)

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["attempt_id"] == "attempt_123"
    for forbidden in ("answers", "telegram_username", "first_name", "result_snapshot", "pdf_last_error", "initData", "secret.example"):
        assert forbidden not in encoded
    router.repository.list_attempts.assert_awaited_once_with(limit=25, offset=5)


@pytest.mark.parametrize("path", ["attempts", "delivery-issues", "notification-issues"])
def test_admin_list_pagination_is_bounded(monkeypatch, path):
    client = make_client(monkeypatch)

    assert client.get(f"/api/admin/diagnostics/{path}?limit=101", auth=ADMIN_AUTH).status_code == 422
    assert client.get(f"/api/admin/diagnostics/{path}?limit=0", auth=ADMIN_AUTH).status_code == 422
    assert client.get(f"/api/admin/diagnostics/{path}?offset=-1", auth=ADMIN_AUTH).status_code == 422


def test_issue_apis_omit_raw_errors_payloads_and_profile_data(monkeypatch):
    from diagnostic.admin import router

    client = make_client(monkeypatch)
    unsafe = {"user_id": 42, "attempt_id": "attempt_123", "status": "failed", "attempts": 2, "last_error": "token=secret", "payload": {"answer": "secret"}, "telegram_username": "private"}
    router.repository.list_delivery_issues.return_value = (1, [unsafe | {"pdf_status": "failed", "pdf_attempts": 2}])
    router.repository.list_notification_issues.return_value = (1, [unsafe | {"id": 7, "kind": "incomplete"}])

    delivery = client.get("/api/admin/diagnostics/delivery-issues", auth=ADMIN_AUTH)
    notifications = client.get("/api/admin/diagnostics/notification-issues", auth=ADMIN_AUTH)
    encoded = json.dumps([delivery.json(), notifications.json()])

    assert delivery.status_code == notifications.status_code == 200
    assert "last_error" not in encoded
    assert "payload" not in encoded
    assert "telegram_username" not in encoded
    assert "token=secret" not in encoded


def test_message_update_is_strict_bounded_and_existing(monkeypatch):
    from diagnostic.admin import router

    client = make_client(monkeypatch)
    router.repository.update_message.return_value = {"key": "WELCOME", "text": "<b>Trusted</b>", "description": "Welcome", "updated_at": None}

    response = client.put("/api/admin/diagnostics/messages/WELCOME", auth=ADMIN_AUTH, json={"text": "<b>Trusted</b>"})

    assert response.status_code == 200
    assert response.json()["text"] == "<b>Trusted</b>"
    router.repository.update_message.assert_awaited_once_with("WELCOME", "<b>Trusted</b>")
    assert client.put("/api/admin/diagnostics/messages/UNKNOWN", auth=ADMIN_AUTH, json={"text": "x"}).status_code == 404
    assert client.put("/api/admin/diagnostics/messages/WELCOME", auth=ADMIN_AUTH, json={"text": "x", "extra": True}).status_code == 422
    assert client.put("/api/admin/diagnostics/messages/WELCOME", auth=ADMIN_AUTH, json={"text": ""}).status_code == 422
    assert client.put("/api/admin/diagnostics/messages/WELCOME", auth=ADMIN_AUTH, json={"text": "x" * 2049}).status_code == 422


@pytest.mark.parametrize(
    "template",
    [
        "{school_name:>1000000000}",
        "{school_name!r}",
        "{school_name.__class__}",
        "{unknown}",
        "<script>bad</script>",
        "<b>unclosed",
        "hello <b",
        "hello &bogus;",
        '<a href="https://">bad link</a>',
        '<a href="https://example.test"><a href="https://example.test">nested</a></a>',
        "hello\x00",
        "hello &#1;",
        "hello &#8232;",
        "We&apos;re ready",
        "<pre><b>nested</b></pre>",
        "<code><i>nested</i></code>",
        "<b><code>nested</code></b>",
    ],
)
def test_message_update_rejects_dangerous_formatting_and_telegram_html(
    monkeypatch, template: str,
):
    client = make_client(monkeypatch)

    response = client.put(
        "/api/admin/diagnostics/messages/WELCOME",
        auth=ADMIN_AUTH,
        json={"text": template},
    )

    assert response.status_code == 422
    from diagnostic.admin import router
    router.repository.update_message.assert_not_awaited()


def test_completion_caption_template_is_validated_at_telegram_limit(monkeypatch):
    client = make_client(monkeypatch)

    response = client.put(
        "/api/admin/diagnostics/messages/QUICK_COMPLETE",
        auth=ADMIN_AUTH,
        json={"text": "x" * 1025},
    )

    assert response.status_code == 422


def test_not_started_template_cannot_claim_an_unknown_subject(monkeypatch):
    client = make_client(monkeypatch)

    response = client.put(
        "/api/admin/diagnostics/messages/NOT_STARTED",
        auth=ADMIN_AUTH,
        json={"text": "Start {subject}."},
    )

    assert response.status_code == 422


def test_allowed_message_missing_from_database_returns_controlled_404(monkeypatch):
    client = make_client(monkeypatch)

    response = client.put("/api/admin/diagnostics/messages/WELCOME", auth=ADMIN_AUTH, json={"text": "Updated"})

    assert response.status_code == 404
    assert response.json() == {"detail": "message_not_found"}


def test_delete_user_requires_positive_id_json_confirmation_and_delete_method(monkeypatch):
    from diagnostic.admin import router

    client = make_client(monkeypatch)
    router.repository.delete_diagnostic_user.return_value = {"notifications": 2, "attempts": 1, "engagements": 1, "offer_events": 1, "funnel_events": 3}

    response = client.request(
        "DELETE", "/api/admin/diagnostics/users", auth=ADMIN_AUTH,
        json={"user_id": 42, "confirm": True},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "deleted": {"notifications": 2, "attempts": 1, "engagements": 1, "offer_events": 1, "funnel_events": 3}}
    call = router.repository.delete_diagnostic_user.await_args
    assert call.args[0] == 42
    assert len(call.args[1]) == 64
    assert len(call.args[2]) == 32
    assert client.request("DELETE", "/api/admin/diagnostics/users", auth=ADMIN_AUTH, json={"user_id": 0, "confirm": True}).status_code == 422
    assert client.request(
        "DELETE", "/api/admin/diagnostics/users", auth=ADMIN_AUTH,
        json={"user_id": 9_223_372_036_854_775_808, "confirm": True},
    ).status_code == 422
    assert client.request("DELETE", "/api/admin/diagnostics/users", auth=ADMIN_AUTH).status_code == 422
    assert client.get("/api/admin/diagnostics/users", auth=ADMIN_AUTH).status_code == 405


def test_admin_is_not_frameable_or_cacheable(monkeypatch):
    client = make_client(monkeypatch)

    response = client.get("/admin/diagnostics", auth=ADMIN_AUTH)

    assert response.headers["content-security-policy"] == "frame-ancestors 'none'"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["cache-control"] == "no-store"


class _Context:
    def __init__(self, value, events, label):
        self.value = value
        self.events = events
        self.label = label

    async def __aenter__(self):
        self.events.append(f"{self.label}:enter")
        return self.value

    async def __aexit__(self, exc_type, *_):
        self.events.append(f"{self.label}:rollback" if exc_type else f"{self.label}:commit")


class _DeleteConnection:
    def __init__(self):
        self.events = []
        self.queries = []

    def transaction(self):
        return _Context(self, self.events, "transaction")

    async def execute(self, sql, *arguments):
        normalized = " ".join(sql.split())
        self.queries.append((normalized, arguments))
        if normalized.startswith("SELECT pg_advisory_xact_lock"):
            return "SELECT 1"
        if normalized.startswith("INSERT INTO diagnostic_erased_users"):
            return "INSERT 0 1"
        if normalized.startswith("INSERT INTO diagnostic_session_generations"):
            return "INSERT 0 1"
        table = normalized.split("FROM", 1)[1].strip().split()[0]
        return {"diagnostic_erased_users": "DELETE 0", "diagnostic_notifications": "DELETE 2", "diagnostic_attempts": "DELETE 1", "diagnostic_engagements": "DELETE 1", "diagnostic_progress_events": "DELETE 1", "diagnostic_offer_events": "DELETE 1", "diagnostic_funnel_events": "DELETE 3", "diagnostic_progress_profiles": "DELETE 1"}[table]


class _DeletePool:
    def __init__(self, connection):
        self.connection = connection

    def acquire(self):
        return _Context(self.connection, self.connection.events, "acquire")


@pytest.mark.asyncio
async def test_delete_repository_is_atomic_parameterized_and_diagnostic_only(monkeypatch):
    from diagnostic.admin import repository

    connection = _DeleteConnection()
    monkeypatch.setattr(repository, "get_pool", AsyncMock(return_value=_DeletePool(connection)))

    result = await repository.delete_diagnostic_user(42, "a" * 64, "b" * 32)

    assert result == {"notifications": 2, "attempts": 1, "engagements": 1, "offer_events": 1, "funnel_events": 3}
    assert connection.events == ["acquire:enter", "transaction:enter", "transaction:commit", "acquire:commit"]
    assert connection.queries[0][0].startswith("SELECT pg_advisory_xact_lock")
    assert connection.queries[1][0].startswith("DELETE FROM diagnostic_erased_users")
    assert connection.queries[2][0].startswith("INSERT INTO diagnostic_erased_users")
    assert connection.queries[3][0].startswith("INSERT INTO diagnostic_session_generations")
    assert connection.queries[3][1] == ("a" * 64, "b" * 32)
    delete_queries = connection.queries[4:]
    assert [query[0].split("FROM ")[1].split()[0] for query in delete_queries] == [
        "diagnostic_notifications", "diagnostic_attempts", "diagnostic_engagements",
        "diagnostic_progress_events", "diagnostic_offer_events", "diagnostic_funnel_events",
        "diagnostic_progress_profiles",
    ]
    assert all(
        ("WHERE subject_hash=$1" in query and arguments == ("a" * 64,))
        if "diagnostic_offer_events" in query or "diagnostic_funnel_events" in query
        else ("WHERE user_id=$1" in query and arguments == (42,))
        for query, arguments in delete_queries
    )
    combined = " ".join(query for query, _ in connection.queries)
    for forbidden in (" users ", "scheduled_jobs", "curator", "slivy", "shared"):
        assert forbidden not in f" {combined.lower()} "
