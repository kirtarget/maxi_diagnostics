from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from diagnostic.catalog import load_catalog
from diagnostic.school import load_school
from diagnostic.settings import Settings


ROOT = Path(__file__).resolve().parents[1]
ADMIN_AUTH = ("admin-user", "admin-password")


def make_client(monkeypatch) -> TestClient:
    from diagnostic.admin import router
    from diagnostic.api.main import create_app

    monkeypatch.setattr(router.repository, "list_content_drafts", AsyncMock(return_value=[]))
    monkeypatch.setattr(router.repository, "get_content_draft", AsyncMock(return_value=None))
    monkeypatch.setattr(router.repository, "create_content_draft", AsyncMock())
    monkeypatch.setattr(router.repository, "save_content_draft", AsyncMock())
    monkeypatch.setattr(router.repository, "record_content_action", AsyncMock())
    settings = Settings(
        "postgresql://unused",
        "123456:test-token",
        "https://app.example",
        "https://app.example",
        ADMIN_AUTH[0],
        ADMIN_AUTH[1],
        None,
    )
    school = load_school(ROOT / "school")
    return TestClient(create_app(settings, school, load_catalog(school)))


def first_diagnostic(client: TestClient):
    return client.app.state.catalog.diagnostics[0]


def draft_row(diagnostic, *, revision: int = 1):
    payload = diagnostic.model_dump(mode="json")
    return {
        "diagnostic_id": diagnostic.id,
        "payload": payload,
        "edit_revision": revision,
        "base_content_version": "a" * 64,
        "payload_sha256": "b" * 64,
        "updated_by": ADMIN_AUTH[0],
        "updated_at": None,
    }


def current_content_version(client: TestClient, diagnostic) -> str:
    return client.app.state.catalog.content_version(
        diagnostic.id,
        client.app.state.settings.application_secret,
    )


def test_content_page_is_protected_and_loads_only_local_content_script(monkeypatch):
    client = make_client(monkeypatch)

    assert client.get("/admin/content").status_code == 401
    response = client.get("/admin/content", auth=ADMIN_AUTH)

    assert response.status_code == 200
    assert "/admin/static/content.js" in response.text
    assert "https://cdn" not in response.text.casefold()


def test_content_index_is_summary_only_and_filterable(monkeypatch):
    client = make_client(monkeypatch)
    diagnostic = first_diagnostic(client)

    response = client.get(
        f"/api/admin/diagnostics/content?exam={diagnostic.exam}&subject={diagnostic.subject}&type={diagnostic.questions[0].type}",
        auth=ADMIN_AUTH,
    )

    assert response.status_code == 200
    encoded = json.dumps(response.json(), ensure_ascii=False)
    assert diagnostic.id in encoded
    assert '"correct"' not in encoded
    assert '"explanation"' not in encoded
    assert response.json()["catalog_question_count"] == sum(
        len(item.questions) for item in client.app.state.catalog.diagnostics
    )
    assert response.json()["diagnostic_question_limit"] == 200
    assert "catalog_question_limit" not in response.json()


def test_create_draft_copies_private_published_document(monkeypatch):
    from diagnostic.admin import router

    client = make_client(monkeypatch)
    diagnostic = first_diagnostic(client)
    row = draft_row(diagnostic)
    router.repository.create_content_draft.return_value = row

    response = client.post(
        f"/api/admin/diagnostics/content/{diagnostic.id}/draft",
        auth=ADMIN_AUTH,
        headers={"Origin": "https://app.example"},
        json={},
    )

    assert response.status_code == 201
    assert response.json()["payload"]["questions"][0]["correct"]
    router.repository.create_content_draft.assert_awaited_once()
    assert router.repository.create_content_draft.await_args.kwargs["actor"] == ADMIN_AUTH[0]


def test_content_mutations_reject_foreign_origin_before_writing(monkeypatch):
    from diagnostic.admin import router

    client = make_client(monkeypatch)
    diagnostic = first_diagnostic(client)

    response = client.post(
        f"/api/admin/diagnostics/content/{diagnostic.id}/draft",
        auth=ADMIN_AUTH,
        headers={"Origin": "https://evil.example"},
        json={},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "admin_origin_invalid"}
    router.repository.create_content_draft.assert_not_awaited()


def test_content_mutations_require_origin_before_writing(monkeypatch):
    from diagnostic.admin import router

    client = make_client(monkeypatch)
    diagnostic = first_diagnostic(client)

    response = client.post(
        f"/api/admin/diagnostics/content/{diagnostic.id}/draft",
        auth=ADMIN_AUTH,
        json={},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "admin_origin_invalid"}
    router.repository.create_content_draft.assert_not_awaited()


def test_question_update_validates_document_and_uses_expected_revision(monkeypatch):
    from diagnostic.admin import router

    client = make_client(monkeypatch)
    diagnostic = first_diagnostic(client)
    current = draft_row(diagnostic, revision=4)
    updated = draft_row(diagnostic, revision=5)
    router.repository.get_content_draft.return_value = current
    router.repository.save_content_draft.return_value = updated
    question = current["payload"]["questions"][0] | {"title": "Проверенное название"}

    response = client.put(
        f"/api/admin/diagnostics/content/{diagnostic.id}/draft/questions/{question['id']}",
        auth=ADMIN_AUTH,
        headers={"Origin": "https://app.example"},
        json={"expected_revision": 4, "question": question},
    )

    assert response.status_code == 200
    call = router.repository.save_content_draft.await_args
    assert call.kwargs["expected_revision"] == 4
    assert call.kwargs["payload"]["questions"][0]["title"] == "Проверенное название"


def test_question_update_rejects_new_asset_outside_published_inventory(monkeypatch):
    from diagnostic.admin import router

    client = make_client(monkeypatch)
    diagnostic = first_diagnostic(client)
    current = draft_row(diagnostic, revision=4)
    router.repository.get_content_draft.return_value = current
    question = current["payload"]["questions"][0] | {
        "asset": "assets/questions/not-published.png"
    }

    response = client.put(
        f"/api/admin/diagnostics/content/{diagnostic.id}/draft/questions/{question['id']}",
        auth=ADMIN_AUTH,
        headers={"Origin": "https://app.example"},
        json={"expected_revision": 4, "question": question},
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "content_asset_not_available"}
    router.repository.save_content_draft.assert_not_awaited()


def test_validate_composes_full_catalog_and_records_no_content(monkeypatch):
    from diagnostic.admin import router

    client = make_client(monkeypatch)
    diagnostic = first_diagnostic(client)
    row = draft_row(diagnostic, revision=7)
    row["base_content_version"] = current_content_version(client, diagnostic)
    router.repository.get_content_draft.return_value = row
    router.repository.record_content_action.return_value = row

    response = client.post(
        f"/api/admin/diagnostics/content/{diagnostic.id}/draft/validate",
        auth=ADMIN_AUTH,
        headers={"Origin": "https://app.example"},
        json={"expected_revision": 7},
    )

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "edit_revision": 7,
        "diagnostic_count": len(client.app.state.catalog.diagnostics),
        "question_count": sum(len(item.questions) for item in client.app.state.catalog.diagnostics),
    }
    call = router.repository.record_content_action.await_args
    assert call.kwargs["action"] == "validated"
    assert "payload" not in call.kwargs


def test_export_is_utf8_without_bom_and_keeps_private_authoring_fields(monkeypatch):
    from diagnostic.admin import router

    client = make_client(monkeypatch)
    diagnostic = first_diagnostic(client)
    row = draft_row(diagnostic, revision=3)
    row["base_content_version"] = current_content_version(client, diagnostic)
    router.repository.get_content_draft.return_value = row
    router.repository.record_content_action.return_value = row

    response = client.post(
        f"/api/admin/diagnostics/content/{diagnostic.id}/draft/export",
        auth=ADMIN_AUTH,
        headers={"Origin": "https://app.example"},
        json={"expected_revision": 3},
    )

    assert response.status_code == 200
    assert response.content.startswith(b"{")
    assert not response.content.startswith(b"\xef\xbb\xbf")
    exported = json.loads(response.content.decode("utf-8"))
    assert exported["questions"][0]["correct"]
    assert response.headers["content-disposition"] == (
        f'attachment; filename="{diagnostic.id}.json"'
    )
    assert router.repository.record_content_action.await_args.kwargs["action"] == "exported"


def test_export_rejects_draft_from_previous_published_version(monkeypatch):
    from diagnostic.admin import router

    client = make_client(monkeypatch)
    diagnostic = first_diagnostic(client)
    row = draft_row(diagnostic, revision=3)
    row["base_content_version"] = "0" * 64
    router.repository.get_content_draft.return_value = row

    response = client.post(
        f"/api/admin/diagnostics/content/{diagnostic.id}/draft/export",
        auth=ADMIN_AUTH,
        headers={"Origin": "https://app.example"},
        json={"expected_revision": 3},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "content_base_changed"}
    router.repository.record_content_action.assert_not_awaited()
