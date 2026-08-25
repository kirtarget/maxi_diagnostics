import asyncio
import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
import pytest_asyncio

from diagnostic.db import attempts, gameplay
from diagnostic.db.core import close_db, get_pool, init_db


pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL is required for PostgreSQL integration tests",
)


@pytest_asyncio.fixture(autouse=True)
async def database():
    await init_db(os.environ["TEST_DATABASE_URL"])
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute(
            """
            TRUNCATE diagnostic_progress_events, diagnostic_completion_ledger,
                     diagnostic_progress_profiles, diagnostic_notifications,
                     diagnostic_attempts, diagnostic_engagements,
                     diagnostic_erased_users, diagnostic_session_generations,
                     diagnostic_report_asset_bundles
            RESTART IDENTITY CASCADE
            """
        )
    yield
    await close_db()


def test_level_thresholds_are_server_derived():
    assert gameplay.level_for_xp(0) == (1, 0)
    assert gameplay.level_for_xp(100) == (2, 0)
    assert gameplay.level_for_xp(250) == (3, 0)
    assert gameplay.level_for_xp(1_400) == (6, 0)


def test_diagnostic_event_uses_server_date_and_deterministic_fingerprint():
    now = datetime(2026, 8, 24, 21, 30, tzinfo=timezone.utc)
    event = gameplay.build_diagnostic_completion_event(
        user_id=9,
        attempt_id="attempt-1",
        mode="quick",
        timezone_name="Europe/Moscow",
        now=now,
    )

    assert event.activity_date.isoformat() == "2026-08-25"
    assert event.idempotency_key == "diagnostic-completion/attempt-1"
    assert event.xp_delta == 20
    assert len(event.fingerprint) == 64


def test_gameplay_serializer_allowlist_excludes_private_columns():
    payload = gameplay.serialize_gameplay_profile(
        {
            "xp_total": 20,
            "streak_days": 1,
            "lives_remaining": 5,
            "daily_goal_target": 1,
            "daily_goal_progress": 1,
            "daily_goal_date": "2026-08-25",
            "quest_key": "complete_3_activities",
            "quest_progress": 1,
            "quest_target": 3,
            "quest_date": "2026-08-25",
            "user_id": 42,
            "answers": {"q1": "A"},
            "correct": "hidden",
            "pdf_document": b"hidden",
        }
    )
    serialized = repr(payload)
    assert "user_id" not in serialized
    assert "answers" not in serialized
    assert "correct" not in serialized
    assert "pdf_document" not in serialized


@pytest.mark.asyncio
async def test_event_retry_and_fingerprint_conflict_are_atomic():
    user_id = 9_100_000_000 + uuid4().int % 100_000_000
    event = gameplay.build_diagnostic_completion_event(
        user_id=user_id,
        attempt_id=f"attempt-{uuid4()}",
        mode="quick",
        now=datetime(2026, 8, 25, 10, tzinfo=timezone.utc),
    )
    pool = await get_pool()
    async with pool.acquire() as connection:
        async with connection.transaction():
            assert await gameplay.apply_gameplay_event(connection, event) is True
            assert await gameplay.apply_gameplay_event(connection, event) is False

            conflicting = gameplay.build_diagnostic_completion_event(
                user_id=user_id,
                attempt_id=event.source_id,
                mode="full",
                now=datetime(2026, 8, 25, 10, tzinfo=timezone.utc),
            )
            with pytest.raises(ValueError, match="diagnostic_progress_event_conflict"):
                await gameplay.apply_gameplay_event(connection, conflicting)

    async with pool.acquire() as connection:
        profile = await gameplay.get_gameplay_profile(connection, user_id)
        assert profile["xp_total"] == 20
        assert profile["streak_days"] == 1
        assert profile["daily_goal_progress"] == 1
        assert profile["quest_progress"] == 1
        assert await connection.fetchval(
            "SELECT count(*) FROM diagnostic_progress_events WHERE user_id=$1", user_id
        ) == 1


@pytest.mark.asyncio
async def test_gameplay_schema_reapply_keeps_one_migration_marker():
    await close_db()
    await init_db(os.environ["TEST_DATABASE_URL"])
    pool = await get_pool()
    async with pool.acquire() as connection:
        assert await connection.fetchval(
            """
            SELECT count(*) FROM diagnostic_schema_migrations
             WHERE version='2026-08-25-kir-91-gameplay-v1'
            """
        ) == 1
        assert await connection.fetchval(
            """
            SELECT count(*) FROM information_schema.columns
             WHERE table_name='diagnostic_progress_profiles' AND column_name='xp_total'
            """
        ) == 1
    await close_db()


@pytest.mark.asyncio
async def test_migration_does_not_retroactively_award_legacy_completion_rows():
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute(
            """
            INSERT INTO diagnostic_completion_ledger (attempt_id, user_id)
            VALUES ('legacy-attempt', 9_300_000_001)
            """
        )
    await close_db()
    await init_db(os.environ["TEST_DATABASE_URL"])
    pool = await get_pool()
    async with pool.acquire() as connection:
        assert await connection.fetchval(
            "SELECT count(*) FROM diagnostic_progress_events WHERE user_id=$1",
            9_300_000_001,
        ) == 0
        assert await connection.fetchval(
            "SELECT count(*) FROM diagnostic_completion_ledger WHERE attempt_id=$1",
            "legacy-attempt",
        ) == 1
    await close_db()


@pytest.mark.asyncio
async def test_concurrent_same_event_projects_once_across_connections():
    user_id = 9_350_000_000 + uuid4().int % 100_000_000
    event = gameplay.build_diagnostic_completion_event(
        user_id=user_id,
        attempt_id=f"attempt-{uuid4()}",
        mode="quick",
        now=datetime(2026, 8, 25, 10, tzinfo=timezone.utc),
    )
    pool = await get_pool()
    first_connection = await pool.acquire()
    second_connection = await pool.acquire()

    async def apply(connection):
        async with connection.transaction():
            await connection.execute("SELECT pg_advisory_xact_lock($1)", user_id)
            return await gameplay.apply_gameplay_event(connection, event)

    try:
        outcomes = await asyncio.gather(
            apply(first_connection),
            apply(second_connection),
        )
    finally:
        await pool.release(first_connection)
        await pool.release(second_connection)

    assert sorted(outcomes) == [False, True]
    async with pool.acquire() as connection:
        assert await connection.fetchval(
            "SELECT count(*) FROM diagnostic_progress_events WHERE user_id=$1", user_id
        ) == 1
        assert await connection.fetchval(
            "SELECT xp_total FROM diagnostic_progress_profiles WHERE user_id=$1", user_id
        ) == 20


@pytest.mark.asyncio
async def test_completion_awards_quick_and_full_once_without_losing_legacy_profile():
    user_id = 9_200_000_000 + uuid4().int % 100_000_000
    await attempts.complete_attempt(
        attempts.AttemptCompletion(
            attempt_id=f"attempt-{uuid4()}", user_id=user_id,
            diagnostic_id="math-10", content_version="a" * 64, exam="ege",
            subject="math", mode="quick", question_count=1,
            progress_revision=1, answers={"q1": "A"}, correct_count=1,
            score=100, max_score=100, score_unit="points", unassessed_part=None,
        )
    )
    full_id = f"attempt-{uuid4()}"
    completion = attempts.AttemptCompletion(
        attempt_id=full_id, user_id=user_id, diagnostic_id="math-10",
        content_version="a" * 64, exam="ege", subject="math", mode="full",
        question_count=1, progress_revision=1, answers={"q1": "A"},
        correct_count=1, score=100, max_score=100, score_unit="points",
        unassessed_part=None,
    )
    await attempts.complete_attempt(completion)
    await attempts.complete_attempt(completion)

    profile = await attempts.get_progress_profile(user_id)
    gameplay_profile = await attempts.get_gameplay_profile(user_id)
    assert profile["completion_count"] == 2
    assert gameplay_profile["xp_total"] == 60
    assert gameplay_profile["lives_remaining"] == 5
