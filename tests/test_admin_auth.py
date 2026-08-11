from __future__ import annotations

import base64
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from diagnostic.catalog import load_catalog
from diagnostic.school import load_school
from diagnostic.settings import Settings


ROOT = Path(__file__).resolve().parents[1]
ADMIN_AUTH = ("admin-user", "admin-password")


def make_client(*, school=None) -> TestClient:
    from diagnostic.api.main import create_app

    settings = Settings(
        "postgresql://unused",
        "123456:test-token",
        "https://app.example",
        "https://app.example",
        ADMIN_AUTH[0],
        ADMIN_AUTH[1],
        None,
    )
    actual_school = school or load_school(ROOT / "school")
    return TestClient(create_app(settings, actual_school, load_catalog(actual_school)))


def test_admin_page_requires_generic_basic_challenge():
    response = make_client().get("/admin/diagnostics")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == 'Basic realm="diagnostic-admin"'
    assert response.json() == {"detail": "Not authenticated"}


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/admin/diagnostics"),
        ("get", "/api/admin/diagnostics/summary"),
        ("get", "/api/admin/diagnostics/attempts"),
        ("get", "/api/admin/diagnostics/delivery-issues"),
        ("get", "/api/admin/diagnostics/notification-issues"),
        ("get", "/api/admin/diagnostics/messages"),
        ("put", "/api/admin/diagnostics/messages/WELCOME"),
        ("delete", "/api/admin/diagnostics/users"),
    ],
)
def test_every_admin_diagnostics_route_requires_auth(method: str, path: str):
    client = make_client()
    response = (
        client.get(path)
        if method == "get"
        else client.request(method.upper(), path, json={})
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == 'Basic realm="diagnostic-admin"'


def test_wrong_username_and_password_have_identical_response_and_both_are_compared(monkeypatch):
    from diagnostic.admin import auth

    calls = []

    def compare(actual, expected):
        calls.append((actual, expected))
        return actual == expected

    monkeypatch.setattr(auth.secrets, "compare_digest", compare)
    client = make_client()
    wrong_user = client.get("/admin/diagnostics", auth=("wrong-user", ADMIN_AUTH[1]))
    wrong_password = client.get("/admin/diagnostics", auth=(ADMIN_AUTH[0], "wrong-password"))

    assert wrong_user.status_code == wrong_password.status_code == 401
    assert wrong_user.json() == wrong_password.json() == {"detail": "Not authenticated"}
    assert len(calls) == 4
    assert all(
        isinstance(actual, bytes) and isinstance(expected, bytes)
        and len(actual) == len(expected) == 32
        for actual, expected in calls
    )
    assert calls[0][0] != calls[0][1]
    assert calls[1][0] == calls[1][1]
    assert calls[2][0] == calls[2][1]
    assert calls[3][0] != calls[3][1]


@pytest.mark.parametrize(
    "authorization",
    [
        None,
        "Bearer token",
        "Basic ",
        "Basic %%%",
        "Basic " + base64.b64encode(b"username-without-colon").decode("ascii"),
        "Basic " + base64.b64encode(b"\xff:password").decode("ascii"),
        "Basic  " + base64.b64encode(b"admin-user:admin-password").decode("ascii"),
        "Basic\t" + base64.b64encode(b"admin-user:admin-password").decode("ascii"),
        "Basic " + ("A" * 2_000),
        "Basic " + base64.b64encode(b"wrong-user:wrong-password").decode("ascii"),
    ],
)
def test_all_invalid_authorization_reaches_two_safe_comparisons_and_same_challenge(
    monkeypatch, authorization
):
    from diagnostic.admin import auth

    calls = []

    def compare(actual, expected):
        calls.append((actual, expected))
        assert isinstance(actual, bytes)
        assert isinstance(expected, bytes)
        assert len(actual) == len(expected) == 32
        return actual == expected

    monkeypatch.setattr(auth.secrets, "compare_digest", compare)
    headers = {} if authorization is None else {"Authorization": authorization}

    response = make_client().get("/admin/diagnostics", headers=headers)

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}
    assert response.headers["www-authenticate"] == 'Basic realm="diagnostic-admin"'
    assert len(calls) == 2


def test_admin_page_uses_autoescaped_school_brand_and_local_static_assets():
    school = load_school(ROOT / "school")
    school.brand.name = '<script id="tenant-xss">alert(1)</script>'

    response = make_client(school=school).get("/admin/diagnostics", auth=ADMIN_AUTH)

    assert response.status_code == 200
    assert '<script id="tenant-xss">' not in response.text
    assert "&lt;script id=&#34;tenant-xss&#34;&gt;" in response.text
    assert "/admin/static/admin.js" in response.text
    assert "https://cdn" not in response.text.lower()


def test_docs_remain_disabled_after_admin_mount():
    client = make_client()

    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
