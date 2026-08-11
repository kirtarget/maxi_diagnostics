from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from urllib.parse import urlencode
from uuid import uuid4

import httpx
import pytest

from diagnostic.catalog import load_catalog
from diagnostic.db.core import close_db, get_pool, init_db
from diagnostic.school import load_school
from diagnostic.settings import Settings


pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL is required for the end-to-end PostgreSQL smoke",
)


def signed_init_data(token: str, user_id: int) -> str:
    pairs = {
        "auth_date": str(int(time.time())),
        "user": json.dumps({"id": user_id, "first_name": "Smoke"}, separators=(",", ":")),
    }
    check_string = "\n".join(f"{key}={pairs[key]}" for key in sorted(pairs))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    pairs["hash"] = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode(pairs)


@pytest.mark.asyncio
async def test_full_configured_diagnostic_persists_one_result_and_queues_one_pdf():
    from diagnostic.api.main import create_app
    from diagnostic.db import attempts

    token = "123456:smoke-test-token-not-for-telegram"
    application_secret = "stable-smoke-installation-secret-123456"
    user_id = 8_000_000_000 + int(uuid4().hex[:6], 16)
    attempt_id = str(uuid4())
    init_data = signed_init_data(token, user_id)
    await init_db(os.environ["TEST_DATABASE_URL"])
    pool = await get_pool()

    async def cleanup() -> None:
        async with pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute("DELETE FROM diagnostic_notifications WHERE user_id=$1", user_id)
                await connection.execute("DELETE FROM diagnostic_attempts WHERE user_id=$1", user_id)
                await connection.execute("DELETE FROM diagnostic_engagements WHERE user_id=$1", user_id)

    await cleanup()
    try:
        settings = Settings(
            os.environ["TEST_DATABASE_URL"], token, "https://app.example",
            "https://app.example", "admin", "password", None,
            application_secret=application_secret,
        )
        school = load_school()
        catalog = load_catalog(school)
        diagnostic = catalog.diagnostics[0]
        questions = catalog.questions_for_mode(diagnostic.id, "full")
        answers = {
            question.id: (
                question.correct[0]
                if question.type == "input"
                else list(question.correct)
                if question.type == "multiple"
                else question.correct
            )
            for question in questions
        }
        app = create_app(settings, school, catalog)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            bootstrap = await client.post(
                "/api/diagnostics/bootstrap", json={"init_data": init_data}
            )
            assert bootstrap.status_code == 200
            session_scope = bootstrap.json()["session_scope"]

            progress = await client.post(
                "/api/diagnostics/session/progress",
                json={
                    "init_data": init_data,
                    "attempt_id": attempt_id,
                    "session_scope": session_scope,
                    "diagnostic_id": diagnostic.id,
                    "content_version": catalog.content_version(
                        diagnostic.id, application_secret
                    ),
                    "mode": "full",
                    "question_index": min(1, len(questions) - 1),
                    "question_count": len(questions),
                    "progress_revision": 1,
                    "answers": {questions[0].id: answers[questions[0].id]},
                },
            )
            assert progress.status_code == 200

            complete = await client.post(
                "/api/diagnostics/session/complete",
                json={
                    "init_data": init_data,
                    "attempt_id": attempt_id,
                    "session_scope": session_scope,
                    "diagnostic_id": diagnostic.id,
                    "content_version": catalog.content_version(
                        diagnostic.id, application_secret
                    ),
                    "progress_revision": 2,
                    "mode": "full",
                    "question_count": len(questions),
                    "answers": answers,
                },
            )
            assert complete.status_code == 200
            assert complete.json()["result"]["score"] == diagnostic.scoring.max_score

            results = await client.post(
                "/api/diagnostics/bootstrap", json={"init_data": init_data}
            )
            assert [row["attempt_id"] for row in results.json()["results"]] == [attempt_id]

        async with pool.acquire() as connection:
            persisted = await connection.fetch(
                "SELECT attempt_id, score, pdf_status FROM diagnostic_attempts WHERE user_id=$1",
                user_id,
            )
        assert len(persisted) == 1
        assert dict(persisted[0]) == {
            "attempt_id": attempt_id,
            "score": diagnostic.scoring.max_score,
            "pdf_status": "pending",
        }
        claimed = await attempts.claim_pending_pdf(attempt_id)
        assert claimed is not None
        assert claimed["attempt_id"] == attempt_id
        assert claimed["pdf_status"] == "sending"
    finally:
        await cleanup()
        await close_db()
