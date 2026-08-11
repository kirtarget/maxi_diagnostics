from pathlib import Path

from fastapi.testclient import TestClient

from diagnostic.catalog import load_catalog
from diagnostic.school import load_school
from diagnostic.settings import Settings


ROOT = Path(__file__).resolve().parents[1]


def make_client() -> TestClient:
    from diagnostic.api.main import create_app

    settings = Settings("postgresql://unused", "token", "https://app.example", "https://app.example", "admin", "password", None)
    school = load_school(ROOT / "school")
    return TestClient(create_app(settings, school, load_catalog(school)))


def test_cors_allows_only_the_configured_miniapp_origin():
    client = make_client()

    allowed = client.options(
        "/api/diagnostics/bootstrap",
        headers={"Origin": "https://app.example", "Access-Control-Request-Method": "POST"},
    )
    denied = client.options(
        "/api/diagnostics/bootstrap",
        headers={"Origin": "https://other.example", "Access-Control-Request-Method": "POST"},
    )

    assert allowed.headers["access-control-allow-origin"] == "https://app.example"
    assert "access-control-allow-origin" not in denied.headers
