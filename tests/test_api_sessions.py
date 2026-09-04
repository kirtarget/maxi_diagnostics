import hashlib
import hmac
import json
import shutil
import time
from pathlib import Path
from urllib.parse import urlencode
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
import pytest

from diagnostic.catalog import load_catalog
from diagnostic.school import load_school
from diagnostic.settings import Settings
from diagnostic.api.sessions import public_school_payload
from diagnostic.session_identity import session_scope


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


def make_client(
    monkeypatch, *, complete_attempt=None, upsert_progress=None, catalog=None,
    get_attempt=None, school=None,
) -> TestClient:
    from diagnostic.api.main import create_app
    from diagnostic.api import sessions

    async def mark_opened(_: int) -> None:
        return None

    monkeypatch.setattr(sessions.attempts, "mark_opened", mark_opened)
    monkeypatch.setattr(
        sessions, "get_session_generation", AsyncMock(return_value=SESSION_GENERATION)
    )
    monkeypatch.setattr(
        sessions, "get_or_create_session_generation", AsyncMock(return_value=SESSION_GENERATION)
    )
    async def no_attempt(*_):
        return None
    monkeypatch.setattr(sessions.attempts, "get_attempt", get_attempt or no_attempt)
    if complete_attempt is not None:
        monkeypatch.setattr(sessions.attempts, "complete_attempt", complete_attempt)
    if upsert_progress is not None:
        monkeypatch.setattr(sessions.attempts, "upsert_progress", upsert_progress)
    settings = Settings(
        "postgresql://unused", "token", "https://app.example",
        "https://app.example", "admin", "password", None,
        application_secret=APPLICATION_SECRET,
    )
    school = school or load_school(SAMPLE_SCHOOL)
    return TestClient(create_app(settings, school, catalog or load_catalog(school)))


def base_completion() -> dict:
    catalog = load_catalog(load_school(SAMPLE_SCHOOL))
    return {
        "init_data": signed_init_data(),
        "attempt_id": "attempt_123",
        "session_scope": SESSION_SCOPE,
        "diagnostic_id": "demo-math",
        "content_version": catalog.content_version("demo-math", APPLICATION_SECRET),
        "progress_revision": 1,
        "mode": "quick",
        "question_count": 2,
        "answers": {"q1": "2", "q2": ["1", "3"]},
    }


def full_completion() -> dict:
    return base_completion() | {
        "mode": "full",
        "question_count": 5,
        "answers": {
            "q1": "2",
            "q2": ["1", "3"],
            "q3": {"a": "2", "b": "1"},
            "q4": "42",
            "q5": "однако",
        },
    }


def test_public_school_payload_omits_server_forecast_rules_and_pdf_copy():
    payload = public_school_payload(load_school(SAMPLE_SCHOOL))
    serialized = json.dumps(payload, ensure_ascii=False)

    assert "recovery_share" not in serialized
    assert '"pdf"' not in serialized
    assert payload["brand"]["interface"]["start_diagnostic"]
    assert payload["brand"]["interface"]["delivery_note"]
    assert '"messages"' not in serialized


def test_public_school_payload_includes_resolved_visual_roles():
    payload = public_school_payload(load_school(SAMPLE_SCHOOL))

    assert payload["brand"]["colors"] == {
        "primary": "#5636D3",
        "accent": "#C7F36B",
        "background": "#F7F5EF",
        "signal": "#D8FF42",
        "ink": "#101517",
        "paper": "#F5F5F0",
    }


def catalog_request() -> dict:
    catalog = load_catalog(load_school(SAMPLE_SCHOOL))
    return {
        "init_data": signed_init_data(),
        "session_scope": SESSION_SCOPE,
        "diagnostic_id": "demo-math",
        "content_version": catalog.content_version(
            "demo-math", APPLICATION_SECRET
        ),
    }


def test_catalog_detail_requires_current_session_and_returns_sanitized_questions(
    monkeypatch,
):
    client = make_client(monkeypatch)

    response = client.post("/api/diagnostics/catalog", json=catalog_request())

    assert response.status_code == 200
    diagnostic = response.json()["diagnostic"]
    assert diagnostic["id"] == "demo-math"
    assert len(diagnostic["questions"]) == 5
    assert diagnostic["question_count"] == len(diagnostic["questions"])
    serialized = json.dumps(diagnostic, ensure_ascii=False)
    assert '"correct"' not in serialized
    assert '"explanation"' not in serialized
    assert '"learning_material_text"' not in serialized
    assert '"learning_material_url"' not in serialized


def test_catalog_detail_rejects_expired_session(monkeypatch):
    client = make_client(monkeypatch)
    body = catalog_request() | {"session_scope": "0" * 24}

    response = client.post("/api/diagnostics/catalog", json=body)

    assert response.status_code == 409
    assert response.json() == {"detail": "session_expired"}


def test_catalog_detail_rejects_stale_content_version(monkeypatch):
    client = make_client(monkeypatch)
    body = catalog_request() | {"content_version": "0" * 64}

    response = client.post("/api/diagnostics/catalog", json=body)

    assert response.status_code == 409
    assert response.json() == {"detail": "diagnostic_content_changed"}


def test_catalog_detail_hides_unknown_diagnostic(monkeypatch):
    client = make_client(monkeypatch)
    body = catalog_request() | {"diagnostic_id": "missing-diagnostic"}

    response = client.post("/api/diagnostics/catalog", json=body)

    assert response.status_code == 404
    assert response.json() == {"detail": "diagnostic_not_found"}


def test_report_asset_bundles_are_deterministic_across_restarts():
    from diagnostic.api.sessions import prepare_report_asset_bundles

    school = load_school(SAMPLE_SCHOOL)
    catalog = load_catalog(school)

    first = prepare_report_asset_bundles(school, catalog)
    assert first == prepare_report_asset_bundles(school, catalog)
    _, payload = first["demo-math"]
    from io import BytesIO
    from zipfile import ZipFile

    with ZipFile(BytesIO(payload)) as archive:
        assert {item.date_time for item in archive.infolist()} == {(1980, 1, 1, 0, 0, 0)}


def test_report_asset_bundle_includes_only_its_diagnostic_images(tmp_path: Path):
    school_root = tmp_path / "school"
    shutil.copytree(SAMPLE_SCHOOL, school_root)
    for name, color in (("question-1.svg", "#111111"), ("question-2.svg", "#222222")):
        (school_root / "assets" / name).write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="10">'
            f'<rect width="20" height="10" fill="{color}"/></svg>',
            encoding="utf-8",
        )
    diagnostic_path = school_root / "diagnostics/demo-math.json"
    data = json.loads(diagnostic_path.read_text(encoding="utf-8"))
    data["questions"][0]["assets"] = ["assets/question-1.svg"]
    diagnostic_path.write_text(json.dumps(data), encoding="utf-8")
    second = dict(data)
    second["id"] = "second-math"
    second["questions"] = [dict(question) for question in data["questions"]]
    second["questions"][0]["assets"] = ["assets/question-2.svg"]
    (school_root / "diagnostics/second-math.json").write_text(
        json.dumps(second), encoding="utf-8"
    )
    school = load_school(school_root)
    catalog = load_catalog(school)

    from diagnostic.api.sessions import prepare_report_asset_bundles
    from io import BytesIO
    from zipfile import ZipFile

    bundles = prepare_report_asset_bundles(school, catalog)
    _, first_payload = bundles["demo-math"]
    _, second_payload = bundles["second-math"]

    with ZipFile(BytesIO(first_payload)) as archive:
        assert "assets/question-1.svg" in archive.namelist()
        assert "assets/question-2.svg" not in archive.namelist()
    with ZipFile(BytesIO(second_payload)) as archive:
        assert "assets/question-2.svg" in archive.namelist()
        assert "assets/question-1.svg" not in archive.namelist()


def test_progress_rejects_unknown_question_id(monkeypatch):
    client = make_client(monkeypatch)
    body = base_completion() | {
        "question_index": 1, "question_count": 2, "progress_revision": 1,
        "answers": {"extra": "x"},
    }

    response = client.post("/api/diagnostics/session/progress", json=body)

    assert response.status_code == 422


def test_progress_maps_attempt_ownership_conflict_to_409(monkeypatch):
    async def upsert_progress(progress):
        assert progress.user_id == 84
        raise ValueError("diagnostic_attempt_conflict")

    client = make_client(monkeypatch, upsert_progress=upsert_progress)
    body = base_completion() | {
        "init_data": signed_init_data(84),
        "question_index": 1,
        "question_count": 2,
        "progress_revision": 1,
    }

    response = client.post("/api/diagnostics/session/progress", json=body)

    assert response.status_code == 409


def test_progress_rejects_coerced_integer_fields(monkeypatch):
    client = make_client(monkeypatch)
    body = base_completion() | {
        "question_index": "1", "question_count": True, "progress_revision": "1",
    }

    response = client.post("/api/diagnostics/session/progress", json=body)

    assert response.status_code == 422


def test_rotated_session_scope_blocks_an_open_pre_erasure_page(monkeypatch):
    from diagnostic.api import sessions

    persisted = AsyncMock()
    client = make_client(monkeypatch, upsert_progress=persisted)
    monkeypatch.setattr(
        sessions, "get_session_generation", AsyncMock(return_value="2" * 32)
    )
    body = base_completion() | {
        "question_index": 1,
        "answers": {"q1": "2"},
    }

    response = client.post("/api/diagnostics/session/progress", json=body)

    assert response.status_code == 409
    assert response.json() == {"detail": "session_expired"}
    persisted.assert_not_awaited()


def test_progress_and_completion_reject_unbounded_revision_churn(monkeypatch):
    client = make_client(monkeypatch)
    body = base_completion() | {"progress_revision": 1001, "question_index": 1}

    assert client.post("/api/diagnostics/session/progress", json=body).status_code == 422
    assert client.post("/api/diagnostics/session/complete", json=body).status_code == 422


@pytest.mark.parametrize(
    ("mode", "question_count", "answers"),
    [
        ("quick", 2, {"q1": "unknown"}),
        ("quick", 2, {"q2": ["1", "1"]}),
        ("quick", 2, {"q2": ["1", "2", "3"]}),
        ("quick", 2, {"q2": ["unknown"]}),
        ("full", 5, {"q3": {"unknown": "1"}}),
        ("full", 5, {"q3": {"a": "unknown"}}),
        ("full", 5, {"q4": " "}),
        ("full", 5, {"q4": "not-a-number"}),
        ("full", 5, {"q4": "42\x00"}),
        ("full", 5, {"q4": "x" * 257}),
        ("full", 5, {"q5": "   "}),
        ("full", 5, {"q5": "но\x00"}),
        ("full", 5, {"q5": "с" * 41}),
        ("full", 5, {"q5": ["но"]}),
    ],
)
def test_progress_rejects_values_that_cannot_be_restored(
    monkeypatch, mode, question_count, answers
):
    client = make_client(monkeypatch)
    body = base_completion() | {
        "mode": mode,
        "question_count": question_count,
        "question_index": 0,
        "answers": answers,
    }

    response = client.post("/api/diagnostics/session/progress", json=body)

    assert response.status_code == 422
    assert response.json()["detail"] == "invalid_answer_value"


@pytest.mark.parametrize(
    ("question_id", "answer"),
    [("q2", ["1"]), ("q3", {"a": "2"})],
)
def test_completion_requires_complete_answer_shapes(monkeypatch, question_id, answer):
    client = make_client(monkeypatch)
    body = full_completion()
    body["answers"][question_id] = answer

    response = client.post("/api/diagnostics/session/complete", json=body)

    assert response.status_code == 422
    assert response.json()["detail"] == "invalid_answer_value"


def test_progress_maps_per_user_limit_to_429(monkeypatch):
    async def upsert_progress(_):
        raise ValueError("diagnostic_rate_limited")

    client = make_client(monkeypatch, upsert_progress=upsert_progress)
    body = base_completion() | {
        "question_index": 1, "question_count": 2, "progress_revision": 1,
    }

    response = client.post("/api/diagnostics/session/progress", json=body)

    assert response.status_code == 429


def test_late_progress_retry_returns_owned_terminal_attempt_after_catalog_change(monkeypatch):
    old_version = "f" * 64

    async def get_attempt(*_):
        return {
            "attempt_id": "attempt_123",
            "diagnostic_id": "demo-math",
            "content_version": old_version,
            "mode": "quick",
            "question_count": 2,
            "question_index": 2,
            "progress_revision": 3,
            "answers": {},
            "status": "completed",
        }

    async def must_not_write(*_):
        raise AssertionError("terminal retry must not write")

    client = make_client(
        monkeypatch, get_attempt=get_attempt, upsert_progress=must_not_write
    )
    body = base_completion() | {
        "content_version": old_version,
        "question_index": 1,
        "progress_revision": 2,
    }

    response = client.post("/api/diagnostics/session/progress", json=body)

    assert response.status_code == 200
    assert response.json()["attempt"]["status"] == "completed"


def test_erased_user_receives_stable_gone_response(monkeypatch):
    from diagnostic.api import sessions

    async def erased(*_):
        raise ValueError("diagnostic_user_erased")

    client = make_client(monkeypatch, upsert_progress=erased)
    body = base_completion() | {
        "question_index": 1, "question_count": 2, "progress_revision": 1,
    }

    progress = client.post("/api/diagnostics/session/progress", json=body)
    monkeypatch.setattr(sessions.attempts, "mark_opened", erased)
    bootstrap = client.post(
        "/api/diagnostics/bootstrap", json={"init_data": body["init_data"]}
    )

    assert progress.status_code == 410
    assert progress.json() == {"detail": "diagnostic_user_erased"}
    assert bootstrap.status_code == 410
    assert bootstrap.json() == {"detail": "diagnostic_user_erased"}


def test_completion_returns_server_scored_result_and_pending_pdf(monkeypatch):
    stored = {}

    async def complete_attempt(completion):
        stored["completion"] = completion
        return {
            "attempt_id": completion.attempt_id,
            "diagnostic_id": completion.diagnostic_id,
            "mode": completion.mode,
            "answers": completion.answers,
            "status": "completed",
            "score": completion.score,
            "correct_count": completion.correct_count,
            "pdf_status": "pending",
            "result_snapshot": completion.result_snapshot,
        }

    client = make_client(monkeypatch, complete_attempt=complete_attempt)

    response = client.post("/api/diagnostics/session/complete", json=base_completion())

    assert response.status_code == 200
    assert response.json()["result"]["score"] == 100
    assert response.json()["attempt"]["pdf_status"] == "pending"
    assert stored["completion"].score == 100
    assert all(
        "correct" not in question
        for question in stored["completion"].report_snapshot["diagnostic"]["questions"]
    )
    assert stored["completion"].forecast == {
        "kind": "accuracy_percent",
        "points": [{"id": "intensive", "label": "Интенсив", "value": 100}],
    }
    assert not hasattr(stored["completion"], "telegram_username")
    assert not hasattr(stored["completion"], "first_name")
    assert response.json()["result"]["forecast"] == stored["completion"].forecast
    assert response.json()["result"]["unassessed_part"] == "оставшаяся часть полной диагностики"


def test_completion_freezes_review_snapshot(monkeypatch):
    stored = {}

    async def complete_attempt(completion):
        stored["snapshot"] = completion.report_snapshot
        return {
            "attempt_id": completion.attempt_id,
            "diagnostic_id": completion.diagnostic_id,
            "mode": completion.mode,
            "status": "completed",
            "pdf_status": "pending",
            "result_snapshot": completion.result_snapshot,
        }

    client = make_client(monkeypatch, complete_attempt=complete_attempt)

    response = client.post("/api/diagnostics/session/complete", json=base_completion())

    assert response.status_code == 200
    review = stored["snapshot"]["review_snapshot"]
    assert review[0]["user_answer"] == "4"
    assert review[0]["expected_answer"] == "4"
    assert review[0]["guidance_kind"] == "individual"
    display_review = stored["snapshot"]["public_review_snapshot"]
    assert display_review[0]["expected_answer"] == "4"
    assert "expected_value" not in display_review[0]


def test_completion_freezes_report_provenance_for_premium_footer(monkeypatch):
    stored = {}

    async def complete_attempt(completion):
        stored["snapshot"] = completion.report_snapshot
        return {
            "attempt_id": completion.attempt_id,
            "diagnostic_id": completion.diagnostic_id,
            "mode": completion.mode,
            "status": "completed",
            "pdf_status": "pending",
            "result_snapshot": completion.result_snapshot,
        }

    client = make_client(monkeypatch, complete_attempt=complete_attempt)
    request = base_completion()

    response = client.post("/api/diagnostics/session/complete", json=request)

    assert response.status_code == 200
    assert stored["snapshot"]["provenance"] == {
        "attempt_id": "attempt_123",
        "diagnostic_id": "demo-math",
        "content_version": request["content_version"],
        "exam": "demo",
        "subject": "Математика",
        "mode": "quick",
    }


def test_review_endpoint_requires_owner_and_completion(monkeypatch):
    from diagnostic.api import sessions

    async def owned_review(_attempt_id, _user_id):
        return {
            "status": "completed",
            "pdf_status": "sent",
            "report_snapshot": {"review_snapshot": [{
                "question_id": "q1", "number": 1, "type": "single", "topic": "topic",
                "title": "Task 1", "prompt": "What is 2 + 2?", "is_correct": False,
                "user_answer": "3", "expected_answer": "4", "guidance": "Add the numbers.",
                "guidance_kind": "individual", "user_value": "1", "expected_value": "2",
            }]},
        }

    monkeypatch.setattr(sessions.attempts, "get_review_attempt", owned_review)
    client = make_client(monkeypatch)
    response = client.post("/api/diagnostics/session/review", json={
        "init_data": signed_init_data(), "attempt_id": "attempt_123", "session_scope": SESSION_SCOPE,
    })

    assert response.status_code == 200
    assert response.json()["available"] is True
    assert response.json()["pdf_status"] == "sent"
    assert "expected_value" not in response.text


def test_review_endpoint_returns_not_found_for_non_owner(monkeypatch):
    from diagnostic.api import sessions

    client = make_client(monkeypatch)
    monkeypatch.setattr(sessions.attempts, "get_review_attempt", AsyncMock(return_value=None))

    response = client.post("/api/diagnostics/session/review", json={
        "init_data": signed_init_data(), "attempt_id": "attempt_123", "session_scope": SESSION_SCOPE,
    })

    assert response.status_code == 404


def test_review_endpoint_rejects_in_progress_attempt(monkeypatch):
    from diagnostic.api import sessions

    client = make_client(monkeypatch)
    monkeypatch.setattr(sessions.attempts, "get_review_attempt", AsyncMock(return_value={
        "status": "in_progress", "pdf_status": None, "report_snapshot": None,
    }))

    response = client.post("/api/diagnostics/session/review", json={
        "init_data": signed_init_data(), "attempt_id": "attempt_123", "session_scope": SESSION_SCOPE,
    })

    assert response.status_code == 409
    assert response.json()["detail"] == "review_not_ready"


def test_review_endpoint_marks_legacy_snapshot_unavailable(monkeypatch):
    from diagnostic.api import sessions

    client = make_client(monkeypatch)
    monkeypatch.setattr(sessions.attempts, "get_review_attempt", AsyncMock(return_value={
        "status": "completed", "pdf_status": "sent", "report_snapshot": {},
    }))

    response = client.post("/api/diagnostics/session/review", json={
        "init_data": signed_init_data(), "attempt_id": "attempt_123", "session_scope": SESSION_SCOPE,
    })

    assert response.status_code == 200
    assert response.json() == {"ok": True, "available": False, "items": [], "pdf_status": "sent"}


def test_completion_reuses_assets_prepared_once_at_app_startup(monkeypatch):
    from diagnostic.api import sessions

    builds = []

    def build_assets(_school, questions):
        builds.append(tuple(question.id for question in questions))
        return b"frozen-assets"

    async def complete_attempt(completion):
        return {
            "attempt_id": completion.attempt_id,
            "status": "completed",
            "pdf_status": "pending",
            "result_snapshot": completion.result_snapshot,
        }

    monkeypatch.setattr(sessions, "_build_report_assets", build_assets)
    client = make_client(monkeypatch, complete_attempt=complete_attempt)
    startup_build_count = len(builds)

    response = client.post("/api/diagnostics/session/complete", json=base_completion())

    assert response.status_code == 200
    assert startup_build_count == 1
    assert len(builds) == startup_build_count


def test_completion_only_enqueues_pdf_for_the_single_worker(monkeypatch):
    from unittest.mock import AsyncMock
    from diagnostic.api import sessions

    events = []

    async def complete_attempt(completion):
        events.append(("persisted", completion.attempt_id))
        return {
            "attempt_id": completion.attempt_id,
            "status": "completed",
            "pdf_status": "pending",
            "completed_transition": True,
            "started_transition": True,
        }

    emitted = AsyncMock()
    monkeypatch.setattr(sessions, "emit_event", emitted)
    client = make_client(monkeypatch, complete_attempt=complete_attempt)

    response = client.post("/api/diagnostics/session/complete", json=base_completion())

    assert response.status_code == 200
    assert events == [("persisted", "attempt_123")]
    assert [call.args[0] for call in emitted.await_args_list] == [
        "diagnostic_started", "diagnostic_completed"
    ]


def test_completion_records_funnel_steps_without_a_telegram_identifier(monkeypatch):
    from unittest.mock import AsyncMock
    from diagnostic.api import sessions
    from diagnostic.session_identity import session_subject_key

    async def complete_attempt(completion):
        return {
            "attempt_id": completion.attempt_id,
            "status": "completed",
            "pdf_status": "pending",
            "completed_transition": True,
            "started_transition": True,
        }

    recorded = AsyncMock()
    monkeypatch.setattr(sessions.funnel, "record_event", recorded)
    client = make_client(monkeypatch, complete_attempt=complete_attempt)

    response = client.post("/api/diagnostics/session/complete", json=base_completion())
    secret = client.app.state.settings.application_secret

    assert response.status_code == 200
    assert [call.kwargs["action"] for call in recorded.await_args_list] == [
        "started", "completed"
    ]
    for call in recorded.await_args_list:
        assert call.kwargs["exam"] and call.kwargs["subject"]
        assert session_subject_key(secret, call.kwargs["user_id"]) is not None
        assert "init_data" not in call.kwargs


def test_completion_accepts_the_server_expected_question_count(monkeypatch):
    async def complete_attempt(completion):
        return {
            "attempt_id": completion.attempt_id,
            "status": "completed",
            "score": completion.score,
            "correct_count": completion.correct_count,
            "pdf_status": "pending",
        }

    client = make_client(monkeypatch, complete_attempt=complete_attempt)

    response = client.post(
        "/api/diagnostics/session/complete",
        json=base_completion() | {"question_count": 2},
    )

    assert response.status_code == 200


def test_completion_rejects_mismatched_question_count(monkeypatch):
    client = make_client(monkeypatch)

    response = client.post(
        "/api/diagnostics/session/complete",
        json=base_completion() | {"question_count": 3},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "invalid_question_count"


def test_completion_rejects_non_integer_question_count(monkeypatch):
    client = make_client(monkeypatch)

    response = client.post(
        "/api/diagnostics/session/complete",
        json=base_completion() | {"question_count": "2"},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "request_invalid"
    assert response.json()["errors"][0]["code"] == "int_type"


def test_completion_rejects_out_of_range_question_count(monkeypatch):
    client = make_client(monkeypatch)

    response = client.post(
        "/api/diagnostics/session/complete",
        json=base_completion() | {"question_count": 201},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "request_invalid"
    assert response.json()["errors"][0]["code"] == "less_than_equal"


def test_completion_rejects_client_score_fields(monkeypatch):
    client = make_client(monkeypatch)

    response = client.post(
        "/api/diagnostics/session/complete",
        json=base_completion() | {"score": 1, "correct_count": 0},
    )

    assert response.status_code == 422


def test_completion_rejects_oversized_answers(monkeypatch):
    client = make_client(monkeypatch)
    body = base_completion() | {"answers": {"q1": "x" * 64000, "q2": ["1", "3"]}}

    response = client.post("/api/diagnostics/session/complete", json=body)

    assert response.status_code == 413


def test_validation_error_never_reflects_rejected_private_input(monkeypatch):
    client = make_client(monkeypatch)
    private_value = "private-signed-payload-that-must-not-be-reflected"

    response = client.post(
        "/api/diagnostics/session/complete",
        json=base_completion() | {"question_count": private_value},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "request_invalid"
    assert private_value not in response.text
    assert len(response.content) < 1024


def test_completion_rejects_malformed_multiple_choice_answer_values(monkeypatch):
    client = make_client(monkeypatch)
    body = base_completion() | {"answers": {"q1": "2", "q2": ["1", 1]}}

    response = client.post("/api/diagnostics/session/complete", json=body)

    assert response.status_code == 422


def test_completion_maps_attempt_ownership_conflict_to_409(monkeypatch):
    async def complete_attempt(_):
        raise ValueError("diagnostic_attempt_conflict")

    client = make_client(monkeypatch, complete_attempt=complete_attempt)

    response = client.post("/api/diagnostics/session/complete", json=base_completion())

    assert response.status_code == 409


def test_completed_attempt_id_cannot_be_reused_for_another_diagnostic_identity(monkeypatch):
    async def get_attempt(*_):
        return {
            "attempt_id": "attempt_123",
            "diagnostic_id": "another-diagnostic",
            "content_version": "f" * 64,
            "mode": "full",
            "question_count": 4,
            "status": "completed",
            "result_snapshot": {"score": 75},
        }

    client = make_client(monkeypatch, get_attempt=get_attempt)

    response = client.post("/api/diagnostics/session/complete", json=base_completion())

    assert response.status_code == 409
    assert response.json() == {"detail": "attempt_conflict"}


def test_repeated_completion_returns_persisted_result_after_catalog_scoring_changes(monkeypatch):
    async def complete_attempt(completion):
        return {
            "attempt_id": completion.attempt_id,
            "diagnostic_id": "demo-math",
            "mode": "quick",
            "answers": {"q1": "1", "q2": ["2"]},
            "status": "completed",
            "pdf_status": "pending",
            "result_snapshot": {
                "diagnostic_id": "demo-math",
                "mode": "quick",
                "correct_count": 1,
                "question_count": 2,
                "score": 50,
                "max_score": 100,
                "score_unit": "accuracy_percent",
                "strong_topics": [],
                "growth_topics": [],
            },
        }

    school = load_school(SAMPLE_SCHOOL)
    catalog = load_catalog(school)
    diagnostic = catalog.get("demo-math")
    changed_catalog = catalog.model_copy(
        update={
            "diagnostics": (
                diagnostic.model_copy(
                    update={"scoring": diagnostic.scoring.model_copy(update={"max_score": 200})}
                ),
            )
        }
    )
    client = make_client(
        monkeypatch, complete_attempt=complete_attempt, catalog=changed_catalog
    )

    response = client.post(
        "/api/diagnostics/session/complete",
        json=base_completion() | {
            "content_version": changed_catalog.content_version(
                "demo-math", APPLICATION_SECRET
            )
        },
    )

    assert response.status_code == 200
    assert response.json()["result"]["score"] == 50


DEMO_SCALE = {
    "id": "demo-mathematics",
    "exam": "demo",
    "subject": "Математика",
    "kind": "test_score",
    "max_primary": 8,
    "min_pass": 27,
    "table": [0, 10, 20, 35, 50, 65, 80, 90, 100],
    "interpolated_primary": [],
    "notes": "",
    "source": {
        "title": "Источник",
        "url": "https://example.org/scale.pdf",
        "date": "2026-05-07",
        "confidence": "secondary",
    },
}


def school_with(*, scales=(), recovery_share=60):
    from diagnostic.school import SCORE_SCALES_ADAPTER

    school = load_school(SAMPLE_SCHOOL)
    offers = [
        offer.model_copy(update={"recovery_share": recovery_share})
        for offer in school.links.offers
    ]
    return school.model_copy(
        update={
            "links": school.links.model_copy(update={"offers": offers}),
            "scales": SCORE_SCALES_ADAPTER.validate_python(
                {"scales": list(scales)}
            ).scales,
        }
    )


def half_correct_completion() -> dict:
    return base_completion() | {"answers": {"q1": "1", "q2": ["1", "3"]}}


def capture_completion(monkeypatch, school):
    stored = {}

    async def complete_attempt(completion):
        stored["completion"] = completion
        return {
            "attempt_id": completion.attempt_id,
            "diagnostic_id": completion.diagnostic_id,
            "mode": completion.mode,
            "status": "completed",
            "score": completion.score,
            "correct_count": completion.correct_count,
            "pdf_status": "pending",
            "result_snapshot": completion.result_snapshot,
        }

    client = make_client(monkeypatch, complete_attempt=complete_attempt, school=school)
    response = client.post(
        "/api/diagnostics/session/complete", json=half_correct_completion()
    )
    assert response.status_code == 200
    return stored["completion"], response.json()


def test_forecast_recovers_a_share_of_the_missed_growth_points(monkeypatch):
    completion, payload = capture_completion(monkeypatch, school_with())

    assert payload["result"]["score"] == 50
    assert payload["result"]["recoverable_primary_score"] == 1
    assert completion.forecast == {
        "kind": "accuracy_percent",
        "points": [{"id": "intensive", "label": "Интенсив", "value": 100}],
    }


def test_forecast_keeps_the_current_value_when_nothing_is_recovered(monkeypatch):
    completion, _ = capture_completion(
        monkeypatch, school_with(recovery_share=0)
    )

    assert completion.forecast["points"][0]["value"] == 50


def test_completion_estimates_the_exam_score_from_the_matching_scale(monkeypatch):
    completion, payload = capture_completion(
        monkeypatch, school_with(scales=[DEMO_SCALE])
    )

    assert payload["result"]["estimate"] == {
        "kind": "test_score",
        "value": 50,
        "scaled_primary": 4,
        "exam_max_primary": 8,
        "sample_max_primary": 2,
        "sample_size": 2,
        "min_pass": 27,
    }
    assert completion.result_snapshot["estimate"] == payload["result"]["estimate"]
    assert completion.forecast == {
        "kind": "test_score",
        "points": [{"id": "intensive", "label": "Интенсив", "value": 100}],
    }


def test_bootstrap_results_carry_the_persisted_estimate(monkeypatch):
    from diagnostic.api.sessions import serialize_attempt

    row = {
        "attempt_id": "attempt_123",
        "diagnostic_id": "demo-math",
        "mode": "quick",
        "status": "completed",
        "score": 50,
        "result_snapshot": {"score": 50, "estimate": {"kind": "grade", "value": 4}},
    }

    assert serialize_attempt(row)["estimate"] == {"kind": "grade", "value": 4}


def test_bootstrap_results_omit_the_estimate_for_older_attempts():
    from diagnostic.api.sessions import serialize_attempt

    row = {
        "attempt_id": "attempt_123",
        "diagnostic_id": "demo-math",
        "mode": "quick",
        "status": "completed",
        "score": 50,
        "result_snapshot": {"score": 50},
    }

    assert "estimate" not in serialize_attempt(row)


def shortened_full_school(tmp_path: Path, full_count: int = 4):
    """A sample school whose full mode stops before the last question."""
    school_root = tmp_path / "school"
    shutil.copytree(SAMPLE_SCHOOL, school_root)
    path = school_root / "diagnostics" / "demo-math.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["full_count"] = full_count
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    school = load_school(school_root)
    return school, load_catalog(school)


def shortened_full_completion(catalog) -> dict:
    return base_completion() | {
        "content_version": catalog.content_version("demo-math", APPLICATION_SECRET),
        "mode": "full",
        "question_count": 4,
        "answers": {
            "q1": "2",
            "q2": ["1", "3"],
            "q3": {"a": "2", "b": "1"},
            "q4": "42",
        },
    }


def test_full_mode_scores_only_the_questions_full_count_covers(monkeypatch, tmp_path):
    school, catalog = shortened_full_school(tmp_path)
    recorded = {}

    async def complete_attempt(completion):
        recorded["completion"] = completion
        return {
            "attempt_id": completion.attempt_id,
            "status": "completed",
            "score": completion.score,
            "correct_count": completion.correct_count,
            "pdf_status": "pending",
        }

    client = make_client(
        monkeypatch, complete_attempt=complete_attempt, catalog=catalog, school=school
    )

    response = client.post(
        "/api/diagnostics/session/complete", json=shortened_full_completion(catalog)
    )

    assert response.status_code == 200
    completion = recorded["completion"]
    assert completion.question_count == 4
    assert [
        question["id"]
        for question in completion.report_snapshot["diagnostic"]["questions"]
    ] == ["q1", "q2", "q3", "q4"]
    assert [
        item["question_id"] for item in completion.report_snapshot["review_snapshot"]
    ] == ["q1", "q2", "q3", "q4"]
    assert catalog.public_summaries(APPLICATION_SECRET)[0]["full_count"] == 4
    assert catalog.public_summaries(APPLICATION_SECRET)[0]["question_count"] == 5


def test_full_mode_rejects_an_answer_beyond_full_count(monkeypatch, tmp_path):
    school, catalog = shortened_full_school(tmp_path)
    client = make_client(monkeypatch, catalog=catalog, school=school)
    body = shortened_full_completion(catalog)
    body["answers"]["q5"] = "однако"
    body["question_count"] = 5

    response = client.post("/api/diagnostics/session/complete", json=body)

    assert response.status_code == 422
    assert response.json()["detail"] == "invalid_question_count"
