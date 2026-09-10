"""PostgreSQL-backed topic-progress behaviour. Skipped without TEST_DATABASE_URL."""

import os
from uuid import uuid4

import pytest
import pytest_asyncio

from diagnostic.db import topic_progress
from diagnostic.db.core import close_db, get_pool, init_db


VERSION = "b" * 64
DIAGNOSTIC = "ege-physics-1206"


@pytest_asyncio.fixture
async def database():
    if not os.getenv("TEST_DATABASE_URL"):
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")
    await init_db(os.environ["TEST_DATABASE_URL"])
    yield
    await close_db()


def new_user_id() -> int:
    return 9_700_000_000 + uuid4().int % 100_000_000


async def seed_profile(user_id: int) -> None:
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute(
            "INSERT INTO diagnostic_progress_profiles (user_id) VALUES ($1)"
            " ON CONFLICT DO NOTHING",
            user_id,
        )


async def record(user_id: int, topic: str, question_id: str, topic_ids: list[str]) -> None:
    pool = await get_pool()
    async with pool.acquire() as connection:
        async with connection.transaction():
            await topic_progress.record_topic_correct(
                connection,
                user_id=user_id,
                diagnostic_id=DIAGNOSTIC,
                content_version=VERSION,
                topic=topic,
                question_id=question_id,
                topic_question_ids=topic_ids,
            )


@pytest.mark.asyncio
async def test_recording_is_idempotent_and_unions_the_correct_set(database):
    user_id = new_user_id()
    await seed_profile(user_id)
    topic_ids = ["p1", "p2", "p3"]

    await record(user_id, "Механика", "p1", topic_ids)
    await record(user_id, "Механика", "p1", topic_ids)  # replay adds nothing
    await record(user_id, "Механика", "p2", topic_ids)

    progress = await topic_progress.get_progress_map(user_id, DIAGNOSTIC, VERSION)
    state = progress["Механика"]
    assert state.correct_ids == frozenset({"p1", "p2"})
    assert state.done_at is None  # p3 still open


@pytest.mark.asyncio
async def test_done_at_is_stamped_once_when_topic_is_complete(database):
    user_id = new_user_id()
    await seed_profile(user_id)
    topic_ids = ["p1", "p2"]

    await record(user_id, "Оптика", "p1", topic_ids)
    await record(user_id, "Оптика", "p2", topic_ids)
    first = (await topic_progress.get_progress_map(user_id, DIAGNOSTIC, VERSION))["Оптика"]
    assert first.done_at is not None

    # A later correct answer to the same closed topic keeps the original stamp.
    await record(user_id, "Оптика", "p1", topic_ids)
    second = (await topic_progress.get_progress_map(user_id, DIAGNOSTIC, VERSION))["Оптика"]
    assert second.done_at == first.done_at


@pytest.mark.asyncio
async def test_progress_is_scoped_by_content_version(database):
    user_id = new_user_id()
    await seed_profile(user_id)
    await record(user_id, "Механика", "p1", ["p1"])
    # A different content version starts empty rather than mixing question sets.
    other = await topic_progress.get_progress_map(user_id, DIAGNOSTIC, "c" * 64)
    assert other == {}


@pytest.mark.asyncio
async def test_today_mode_session_with_a_topic_is_accepted(database):
    """The trainer-session constraints allow a scored today session on a topic."""
    from diagnostic.db import trainer

    user_id = new_user_id()
    await seed_profile(user_id)
    session, _ = await trainer.start_session(
        session_id="T" + "0" * 31,
        user_id=user_id,
        diagnostic_id=DIAGNOSTIC,
        content_version=VERSION,
        mode="today",
        selected_question_ids=["p1", "p2"],
        topic="Механика",
    )
    assert session["mode"] == "today"
    assert session["topic"] == "Механика"


@pytest.mark.asyncio
async def test_schema_reapplies_cleanly_and_keeps_rows(database):
    """Re-running the whole DDL is idempotent and preserves recorded progress."""
    user_id = new_user_id()
    await seed_profile(user_id)
    await record(user_id, "Механика", "p1", ["p1", "p2"])

    # init_db runs the full DDL again against the same database.
    await init_db(os.environ["TEST_DATABASE_URL"])

    progress = await topic_progress.get_progress_map(user_id, DIAGNOSTIC, VERSION)
    assert progress["Механика"].correct_ids == frozenset({"p1"})
