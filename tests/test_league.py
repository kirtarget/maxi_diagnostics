import hashlib
import json
import os
from datetime import date, datetime, timezone

import pytest
import pytest_asyncio

from diagnostic.db import league
from diagnostic.db.core import close_db, get_pool, init_db


pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL is required for PostgreSQL integration tests",
)

SECRET = "stable-installation-secret-1234567890"
TZ = "Europe/Moscow"


@pytest_asyncio.fixture(autouse=True)
async def database():
    await init_db(os.environ["TEST_DATABASE_URL"])
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute("TRUNCATE diagnostic_progress_events RESTART IDENTITY CASCADE")
    yield
    await close_db()


def test_week_uses_monday_sunday_in_configured_timezone():
    sunday = datetime(2026, 8, 23, 20, 59, tzinfo=timezone.utc)
    monday = datetime(2026, 8, 23, 21, 1, tzinfo=timezone.utc)

    before = league.current_week(timezone_name=TZ, now=sunday)
    after = league.current_week(timezone_name=TZ, now=monday)

    assert (before.key, before.start.isoformat(), before.end.isoformat()) == (
        "2026-08-17", "2026-08-17", "2026-08-23"
    )
    assert (after.key, after.start.isoformat(), after.end.isoformat()) == (
        "2026-08-24", "2026-08-24", "2026-08-30"
    )


def test_pseudonym_and_bucket_are_deterministic_and_secret_scoped():
    assert league.cohort_bucket(SECRET, "2026-08-24", 42) == league.cohort_bucket(
        SECRET, "2026-08-24", 42
    )
    assert league.pseudonym(SECRET, "2026-08-24", 42).startswith("Игрок ")
    assert len(league.pseudonym(SECRET, "2026-08-24", 42).split()[1]) == 8
    assert league.pseudonym("other-secret", "2026-08-24", 42) != league.pseudonym(
        SECRET, "2026-08-24", 42
    )


async def _insert_event(connection, user_id: int, activity_date: str, xp: int, index: int):
    key = f"league-test/{user_id}/{index}"
    fingerprint = hashlib.sha256(key.encode("ascii")).hexdigest()
    await connection.execute(
        """
        INSERT INTO diagnostic_progress_events (
            user_id, idempotency_key, fingerprint, event_type, source_type,
            source_id, activity_date, xp_delta
        ) VALUES ($1,$2,$3,'trainer_answer_correct','trainer_answer',$2,$4::date,$5)
        """,
        user_id, key, fingerprint, date.fromisoformat(activity_date), xp,
    )


def _users_in_bucket(week_key: str, bucket: int, count: int) -> list[int]:
    users = []
    candidate = 10_000
    while len(users) < count:
        if league.cohort_bucket(SECRET, week_key, candidate) == bucket:
            users.append(candidate)
        candidate += 1
    return users


@pytest.mark.asyncio
async def test_weekly_aggregation_ignores_negative_old_and_other_cohort_events():
    now = datetime(2026, 8, 25, 10, tzinfo=timezone.utc)
    bucket = league.cohort_bucket(SECRET, "2026-08-24", 42)
    users = [42, *_users_in_bucket("2026-08-24", bucket, 5)]
    users = list(dict.fromkeys(users))
    pool = await get_pool()
    async with pool.acquire() as connection:
        for index, user_id in enumerate(users):
            await _insert_event(connection, user_id, "2026-08-25", 10 + index, index)
        await _insert_event(connection, users[0], "2026-08-25", -100, 99)
        await _insert_event(connection, users[0], "2026-08-23", 1000, 100)
        other = next(
            value for value in range(20_000, 21_000)
            if league.cohort_bucket(SECRET, "2026-08-24", value) != bucket
        )
        await _insert_event(connection, other, "2026-08-25", 1000, 101)

        payload = await league.get_weekly_league(
            connection, user_id=42, application_secret=SECRET, timezone_name=TZ, now=now
        )

    assert payload["status"] == "active"
    assert payload["participant_count"] == len(users)
    assert payload["me"]["xp_week"] == 10
    assert len(payload["rows"]) == min(10, len(users))
    assert all(set(row) == {"rank", "display_label", "xp_week", "is_me"} for row in payload["rows"])
    assert all(row["xp_week"] > 0 for row in payload["rows"])
    assert "user_id" not in json.dumps(payload, ensure_ascii=False)
    assert "trainer_answer_correct" not in json.dumps(payload, ensure_ascii=False)


@pytest.mark.asyncio
async def test_forming_league_hides_peer_rows_until_five_participants():
    now = datetime(2026, 8, 25, 10, tzinfo=timezone.utc)
    pool = await get_pool()
    async with pool.acquire() as connection:
        await _insert_event(connection, 42, "2026-08-25", 20, 1)
        await _insert_event(connection, 43, "2026-08-25", 10, 2)
        await _insert_event(connection, 44, "2026-08-25", 5, 3)
        await _insert_event(connection, 45, "2026-08-25", 1, 4)
        payload = await league.get_weekly_league(
            connection, user_id=42, application_secret=SECRET, timezone_name=TZ, now=now
        )

    assert payload["status"] == "forming"
    assert payload["rows"] == []
    assert payload["me"]["xp_week"] == 20


@pytest.mark.asyncio
async def test_active_league_limits_rows_and_uses_competition_ranks_for_ties():
    now = datetime(2026, 8, 25, 10, tzinfo=timezone.utc)
    bucket = league.cohort_bucket(SECRET, "2026-08-24", 42)
    users = [42, *_users_in_bucket("2026-08-24", bucket, 32)]
    users = list(dict.fromkeys(users))
    pool = await get_pool()
    async with pool.acquire() as connection:
        for index, user_id in enumerate(users):
            await _insert_event(connection, user_id, "2026-08-25", 100 if index < 3 else index, index)
        payload = await league.get_weekly_league(
            connection, user_id=42, application_secret=SECRET, timezone_name=TZ, now=now
        )

    assert payload["participant_count"] == 30
    assert len(payload["rows"]) == 10
    assert payload["rows"][0]["rank"] == 1
    assert sum(row["xp_week"] == 100 for row in payload["rows"]) == 3
    assert payload["me"]["rank"] == 1


@pytest.mark.asyncio
async def test_user_outside_bounded_cohort_keeps_xp_but_has_no_public_rank():
    now = datetime(2026, 8, 25, 10, tzinfo=timezone.utc)
    bucket = league.cohort_bucket(SECRET, "2026-08-24", 42)
    users = [42, *_users_in_bucket("2026-08-24", bucket, 32)]
    users = list(dict.fromkeys(users))
    pool = await get_pool()
    async with pool.acquire() as connection:
        for index, user_id in enumerate(users):
            xp = 1 if user_id == 42 else 100 + index
            await _insert_event(connection, user_id, "2026-08-25", xp, index)
        payload = await league.get_weekly_league(
            connection, user_id=42, application_secret=SECRET, timezone_name=TZ, now=now
        )

    assert payload["status"] == "active"
    assert payload["me"] == {"rank": None, "xp_week": 1}
    assert all(not row["is_me"] for row in payload["rows"])
