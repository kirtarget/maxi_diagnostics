import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio

from diagnostic.db import offer_events
from diagnostic.db.core import close_db, get_pool, init_db
from diagnostic.session_identity import session_subject_key


pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL is required for PostgreSQL integration tests",
)


@pytest_asyncio.fixture(autouse=True)
async def database():
    await init_db(os.environ["TEST_DATABASE_URL"])
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute("TRUNCATE diagnostic_offer_events")
    yield
    await close_db()


def subject(user_id: int = 42) -> str:
    return session_subject_key("stable-installation-secret-1234567890", user_id)


@pytest.mark.asyncio
async def test_event_retry_is_idempotent_and_changed_payload_conflicts():
    pool = await get_pool()
    event_id = f"evt_{uuid4().hex}"
    async with pool.acquire() as connection:
        async with connection.transaction():
            assert await offer_events.record_offer_event(
                connection,
                event_id=event_id,
                subject_hash=subject(),
                placement="home",
                offer_id="exam-preparation",
                event_type="impression",
            ) is True
            assert await offer_events.record_offer_event(
                connection,
                event_id=event_id,
                subject_hash=subject(),
                placement="home",
                offer_id="exam-preparation",
                event_type="impression",
            ) is False
            with pytest.raises(ValueError, match="offer_event_conflict"):
                await offer_events.record_offer_event(
                    connection,
                    event_id=event_id,
                    subject_hash=subject(),
                    placement="trainer",
                    offer_id="exam-preparation",
                    event_type="click",
                )
    async with pool.acquire() as connection:
        assert await connection.fetchval("SELECT count(*) FROM diagnostic_offer_events") == 1
        assert await connection.fetchval(
            "SELECT count(*) FROM diagnostic_offer_events WHERE subject_hash=$1", subject()
        ) == 1


@pytest.mark.asyncio
async def test_rate_limit_is_per_pseudonymous_subject_and_retention_is_bounded():
    pool = await get_pool()
    now = datetime.now(timezone.utc)
    async with pool.acquire() as connection:
        async with connection.transaction():
            for index in range(2):
                assert await offer_events.record_offer_event(
                    connection,
                    event_id=f"evt_{uuid4().hex}",
                    subject_hash=subject(),
                    placement="home",
                    offer_id="exam-preparation",
                    event_type="click",
                    now=now,
                    max_events_per_hour=2,
                ) is True
            with pytest.raises(ValueError, match="offer_event_rate_limited"):
                await offer_events.record_offer_event(
                    connection,
                    event_id=f"evt_{uuid4().hex}",
                    subject_hash=subject(),
                    placement="home",
                    offer_id="exam-preparation",
                    event_type="click",
                    now=now,
                    max_events_per_hour=2,
                )
            assert await offer_events.record_offer_event(
                connection,
                event_id=f"evt_{uuid4().hex}",
                subject_hash=subject(43),
                placement="home",
                offer_id="exam-preparation",
                event_type="click",
                now=now,
                max_events_per_hour=2,
            ) is True
            await connection.execute(
                "UPDATE diagnostic_offer_events SET occurred_at=$1",
                now - timedelta(days=91),
            )
            assert await offer_events.purge_offer_events(
                connection, retention_days=90, limit=2
            ) == 2


@pytest.mark.asyncio
async def test_subject_erasure_removes_pseudonymous_events():
    pool = await get_pool()
    async with pool.acquire() as connection:
        async with connection.transaction():
            await offer_events.record_offer_event(
                connection,
                event_id=f"evt_{uuid4().hex}",
                subject_hash=subject(),
                placement="home",
                offer_id="exam-preparation",
                event_type="dismiss",
            )
            await connection.execute(
                "DELETE FROM diagnostic_offer_events WHERE subject_hash=$1", subject()
            )
    async with pool.acquire() as connection:
        assert await connection.fetchval(
            "SELECT count(*) FROM diagnostic_offer_events WHERE subject_hash=$1", subject()
        ) == 0
