from unittest.mock import AsyncMock

from test_api_sessions import make_client, signed_init_data, SESSION_SCOPE
from test_admin_diagnostics import make_client as make_admin, ADMIN_AUTH


def test_onboarding_rejects_invalid_identity_and_scope(monkeypatch):
    from diagnostic.api import sessions
    client = make_client(monkeypatch)
    start = AsyncMock(return_value=True)
    monkeypatch.setattr(sessions.onboarding, "start_selection", start)
    body = {"init_data": "invalid", "session_scope": SESSION_SCOPE, "status": "selection"}
    assert client.post("/api/diagnostics/onboarding", json=body).status_code == 403
    body.update(init_data=signed_init_data(), session_scope="0" * 24)
    assert client.post("/api/diagnostics/onboarding", json=body).status_code == 409
    start.assert_not_awaited()


def test_onboarding_cannot_set_completed_from_client(monkeypatch):
    client = make_client(monkeypatch)
    response = client.post("/api/diagnostics/onboarding", json={
        "init_data": signed_init_data(), "session_scope": SESSION_SCOPE, "status": "completed",
    })
    assert response.status_code == 422


def test_onboarding_selection_is_persisted_before_acknowledgement(monkeypatch):
    from diagnostic.api import sessions
    client = make_client(monkeypatch)
    start = AsyncMock(return_value=True)
    monkeypatch.setattr(sessions.onboarding, "start_selection", start)
    monkeypatch.setattr(sessions.onboarding, "get_status", AsyncMock(return_value="selection"))
    monkeypatch.setattr(sessions.funnel, "record_event", AsyncMock(return_value=True))
    response = client.post("/api/diagnostics/onboarding", json={
        "init_data": signed_init_data(), "session_scope": SESSION_SCOPE, "status": "selection",
    })
    assert response.status_code == 200
    assert response.json() == {"status": "selection"}
    start.assert_awaited_once_with(42)


def test_users_page_is_protected_and_escapes_subject(monkeypatch):
    from diagnostic.admin import router
    client = make_admin(monkeypatch)
    listing = AsyncMock(return_value=[{
        "user_id": 42, "opened_at": "2026-09-06", "last_opened_at": "2026-09-06",
        "subject": "<script>alert(1)</script>", "started": 1, "completed": 0,
        "correct_count": None, "question_count": None, "streak_days": 0,
        "streak_last_date": None, "lives_remaining": 5, "lives_refill_at": None,
        "notifications_enabled": False, "errors": 0,
    }])
    monkeypatch.setattr(router.repository, "list_users", listing)
    assert client.get("/admin/users").status_code == 401
    response = client.get("/admin/users?user_id=42", auth=ADMIN_AUTH)
    assert response.status_code == 200
    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;" in response.text
    listing.assert_awaited_once_with(offset=0, user_id=42)
