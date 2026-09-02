import os
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

from diagnostic.db import funnel
from diagnostic.db.core import close_db, get_pool, init_db
from diagnostic.session_identity import session_subject_key


pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
SECRET = "stable-installation-secret-1234567890"


@pytest_asyncio.fixture(autouse=True)
async def database():
    await init_db(os.environ["TEST_DATABASE_URL"])
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute("TRUNCATE diagnostic_funnel_events")
    yield
    await close_db()


def subject(user_id: int) -> str:
    return session_subject_key(SECRET, user_id)


async def seed(rows) -> None:
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.executemany(
            """
            INSERT INTO diagnostic_funnel_events
                (subject_hash, action, exam, subject, occurred_on, occurred_at)
            VALUES ($1, $2, $3, $4, $5::date, ($5::date)::timestamptz)
            """,
            rows,
        )


def days_ago(count: int):
    """Seed against the UTC calendar the aggregation windows are defined in."""
    return datetime.now(timezone.utc).date() - timedelta(days=count)


@pytest.mark.asyncio
async def test_funnel_counts_unique_subjects_per_step_and_return_windows():
    await seed(
        [
            (subject(1), "opened", None, None, days_ago(3)),
            (subject(1), "opened", None, None, days_ago(3)),
            (subject(1), "started", "oge", "Математика", days_ago(3)),
            (subject(1), "completed", "oge", "Математика", days_ago(3)),
            (subject(1), "result_viewed", "oge", "Математика", days_ago(2)),
            (subject(1), "trainer_answered", "oge", "Математика", days_ago(2)),
            (subject(2), "opened", None, None, days_ago(6)),
            (subject(2), "started", "ege", "Физика", days_ago(6)),
            (subject(2), "offer_clicked", None, None, days_ago(1)),
            (subject(3), "opened", None, None, days_ago(20)),
        ]
    )

    week = await funnel.funnel_report(days=7)
    month = await funnel.funnel_report(days=30)

    assert week["summary"] == {
        "subjects": 2,
        "opened": 2,
        "started": 2,
        "completed": 1,
        "result_viewed": 1,
        "trainer_answered": 1,
        "offer_clicked": 1,
        "returned_d1": 1,
        "returned_d7": 1,
    }
    assert month["summary"]["opened"] == 3
    assert month["summary"]["subjects"] == 3


@pytest.mark.asyncio
async def test_funnel_breakdown_and_filters_stay_inside_the_window():
    await seed(
        [
            (subject(1), "started", "oge", "Математика", days_ago(1)),
            (subject(2), "started", "oge", "Математика", days_ago(1)),
            (subject(2), "completed", "oge", "Математика", days_ago(1)),
            (subject(3), "started", "ege", "Физика", days_ago(1)),
        ]
    )

    report = await funnel.funnel_report(days=7)
    filtered = await funnel.funnel_report(days=7, exam="ege")

    assert report["breakdown"] == [
        {
            "exam": "ege", "subject": "Физика", "started": 1, "completed": 0,
            "result_viewed": 0, "trainer_answered": 0,
        },
        {
            "exam": "oge", "subject": "Математика", "started": 2, "completed": 1,
            "result_viewed": 0, "trainer_answered": 0,
        },
    ]
    assert filtered["exam"] == "ege"
    assert filtered["summary"]["started"] == 1
    assert filtered["summary"]["completed"] == 0


@pytest.mark.asyncio
async def test_recorded_events_purge_after_the_retention_window():
    assert await funnel.record_event(
        application_secret=SECRET, user_id=7, action="opened"
    ) is True
    pool = await get_pool()
    async with pool.acquire() as connection:
        assert await connection.fetchval(
            "SELECT count(*) FROM diagnostic_funnel_events WHERE subject_hash=$1",
            subject(7),
        ) == 1
        assert await funnel.purge_funnel_events(connection, retention_days=90) == 0
        await connection.execute(
            "UPDATE diagnostic_funnel_events SET occurred_at=now() - interval '91 days'"
        )
        assert await funnel.purge_funnel_events(connection, retention_days=90) == 1
        assert await connection.fetchval(
            "SELECT count(*) FROM diagnostic_funnel_events"
        ) == 0
        with pytest.raises(ValueError, match="invalid_funnel_event_retention"):
            await funnel.purge_funnel_events(connection, retention_days=0)
