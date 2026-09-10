"""PostgreSQL-backed checkpoint persistence. Skipped without TEST_DATABASE_URL."""

import os
from uuid import uuid4

import pytest
import pytest_asyncio

from diagnostic.db import topic_checkpoints
from diagnostic.db.core import close_db, get_pool, init_db


VERSION = "d" * 64
DIAGNOSTIC = "ege-physics-1206"


@pytest_asyncio.fixture
async def database():
    if not os.getenv("TEST_DATABASE_URL"):
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")
    await init_db(os.environ["TEST_DATABASE_URL"])
    yield
    await close_db()


def new_user_id() -> int:
    return 9_500_000_000 + uuid4().int % 100_000_000


async def seed_profile(user_id: int) -> None:
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute(
            "INSERT INTO diagnostic_progress_profiles (user_id) VALUES ($1)"
            " ON CONFLICT DO NOTHING",
            user_id,
        )


@pytest.mark.asyncio
async def test_record_pass_is_immutable_on_replay(database):
    user_id = new_user_id()
    await seed_profile(user_id)

    first = await topic_checkpoints.record_pass(
        user_id=user_id, diagnostic_id=DIAGNOSTIC, content_version=VERSION,
        unit_index=0, session_id="s" * 32, correct_count=4, question_count=5,
    )
    # A replay with different counts keeps the original immutable pass.
    second = await topic_checkpoints.record_pass(
        user_id=user_id, diagnostic_id=DIAGNOSTIC, content_version=VERSION,
        unit_index=0, session_id="s" * 32, correct_count=1, question_count=5,
    )
    assert first.passed_at == second.passed_at
    assert second.mastered_count == 4

    passed = await topic_checkpoints.get_passed_map(user_id, DIAGNOSTIC, VERSION)
    assert set(passed) == {0}
    assert passed[0].question_total == 5


@pytest.mark.asyncio
async def test_passed_map_is_scoped_by_content_version(database):
    user_id = new_user_id()
    await seed_profile(user_id)
    await topic_checkpoints.record_pass(
        user_id=user_id, diagnostic_id=DIAGNOSTIC, content_version=VERSION,
        unit_index=1, session_id=None, correct_count=3, question_count=3,
    )
    other = await topic_checkpoints.get_passed_map(user_id, DIAGNOSTIC, "e" * 64)
    assert other == {}


@pytest.mark.asyncio
async def test_start_checkpoint_session_persists_and_resumes_by_question_set(database):
    from diagnostic.db import trainer

    user_id = new_user_id()
    await seed_profile(user_id)
    question_ids = ["sp-q1", "sp-q2", "sp-q3"]

    session, _ = await trainer.start_checkpoint_session(
        session_id="K" + "0" * 31,
        user_id=user_id,
        diagnostic_id=DIAGNOSTIC,
        content_version=VERSION,
        selected_question_ids=question_ids,
    )
    assert session["mode"] == "checkpoint"
    assert session["topic"] is None
    assert session["question_ids"] == question_ids

    # A second start with the same set resumes the same session, not a new one.
    resumed, _ = await trainer.start_checkpoint_session(
        session_id="K" + "1" * 31,
        user_id=user_id,
        diagnostic_id=DIAGNOSTIC,
        content_version=VERSION,
        selected_question_ids=question_ids,
    )
    assert resumed["trainer_session_id"] == session["trainer_session_id"]

    # A different unit's set starts its own session.
    other, _ = await trainer.start_checkpoint_session(
        session_id="K" + "2" * 31,
        user_id=user_id,
        diagnostic_id=DIAGNOSTIC,
        content_version=VERSION,
        selected_question_ids=["sp-q4", "sp-q5"],
    )
    assert other["trainer_session_id"] != session["trainer_session_id"]


@pytest.mark.asyncio
async def test_schema_reapplies_cleanly_and_keeps_rows(database):
    user_id = new_user_id()
    await seed_profile(user_id)
    await topic_checkpoints.record_pass(
        user_id=user_id, diagnostic_id=DIAGNOSTIC, content_version=VERSION,
        unit_index=0, session_id=None, correct_count=5, question_count=5,
    )
    # Re-running the whole DDL is idempotent and preserves the passed row.
    await init_db(os.environ["TEST_DATABASE_URL"])
    passed = await topic_checkpoints.get_passed_map(user_id, DIAGNOSTIC, VERSION)
    assert passed[0].mastered_count == 5
