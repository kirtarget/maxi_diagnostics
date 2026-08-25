from datetime import datetime, timedelta, timezone
import asyncio
import json
import os
from uuid import uuid4

import pytest
import pytest_asyncio

from diagnostic.db import trainer
from diagnostic.db.core import close_db, get_pool, init_db
from diagnostic.db import gameplay
from diagnostic.db.schema import DDL


@pytest_asyncio.fixture
async def database():
    if not os.getenv("TEST_DATABASE_URL"):
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")
    await init_db(os.environ["TEST_DATABASE_URL"])
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute(
            """
            TRUNCATE diagnostic_mistakes, diagnostic_trainer_answers, diagnostic_trainer_sessions,
                     diagnostic_progress_events, diagnostic_progress_profiles,
                     diagnostic_erased_users, diagnostic_session_generations
            RESTART IDENTITY CASCADE
            """
        )
    yield
    await close_db()


def test_lives_refill_is_pure_and_caps_at_five():
    refill_at = datetime(2026, 8, 25, 8, tzinfo=timezone.utc)
    assert gameplay.reconcile_lives(
        2, refill_at, now=refill_at + timedelta(hours=3, minutes=59)
    ) == (2, refill_at)
    assert gameplay.reconcile_lives(
        2, refill_at, now=refill_at + timedelta(hours=8)
    ) == (4, refill_at + timedelta(hours=8))
    assert gameplay.reconcile_lives(
        2, refill_at, now=refill_at + timedelta(hours=20)
    ) == (5, None)


def test_trainer_schema_has_separate_session_and_answer_ownership():
    assert "CREATE TABLE IF NOT EXISTS diagnostic_trainer_sessions" in DDL
    assert "CREATE TABLE IF NOT EXISTS diagnostic_trainer_answers" in DDL
    assert "UNIQUE (session_id, question_id)" in DDL
    assert "ON DELETE CASCADE" in DDL
    assert "CREATE TABLE IF NOT EXISTS diagnostic_mistakes" in DDL
    assert "PRIMARY KEY (user_id, diagnostic_id, question_id)" in DDL
    assert "source_attempt_id" in DDL


def test_trainer_event_is_server_scoped_and_deterministic():
    now = datetime(2026, 8, 25, 10, tzinfo=timezone.utc)
    event = gameplay.build_trainer_answer_event(
        user_id=42, session_id="A" * 32, question_id="q1", now=now
    )
    assert event.event_type == "trainer_answer_correct"
    assert event.source_type == "trainer_answer"
    assert event.idempotency_key == f"trainer-answer/{'A' * 32}/q1"
    assert event.xp_delta == 10
    assert len(event.fingerprint) == 64


async def _start(user_id: int, *, count: int = 1):
    session_id = f"trainer_{uuid4().hex}"
    return session_id, await trainer.start_session(
        session_id=session_id,
        user_id=user_id,
        diagnostic_id="math-10",
        content_version="a" * 64,
        mode="normal",
        selected_question_ids=[f"q{index}" for index in range(count)],
    )


async def _source_attempt(user_id: int, attempt_id: str, *, snapshot: dict):
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute(
            """
            INSERT INTO diagnostic_attempts (
                attempt_id, user_id, diagnostic_id, content_version,
                exam, subject, mode, status, question_count, completed_at,
                report_snapshot
            ) VALUES ($1,$2,'math-10',$3,'ege','math','full','completed',1,now(),$4::jsonb)
            """,
            attempt_id, user_id, "a" * 64, json.dumps(snapshot, ensure_ascii=False),
        )


@pytest.mark.asyncio
async def test_answer_retry_projects_xp_once_and_finish_is_idempotent(database):
    user_id = 9_800_000_000 + uuid4().int % 100_000_000
    session_id, (session, _) = await _start(user_id)
    key = "answer-1"
    fingerprint = trainer.answer_fingerprint(
        session_id=session_id, question_id="q0", answer="A", revision=1,
        idempotency_key=key,
    )
    first = await trainer.answer_question(
        session_id=session_id, user_id=user_id, question_id="q0", answer="A",
        revision=1, idempotency_key=key, fingerprint=fingerprint, is_correct=True,
        public_feedback={"correct_answer": "A", "explanation": "ok"},
    )
    retry = await trainer.answer_question(
        session_id=session_id, user_id=user_id, question_id="q0", answer="A",
        revision=1, idempotency_key=key, fingerprint=fingerprint, is_correct=True,
        public_feedback={"correct_answer": "A", "explanation": "ok"},
    )
    assert first == retry
    finished = await trainer.finish_session(
        session_id=session_id, user_id=user_id, revision=2
    )
    assert finished["correct_count"] == 1
    assert finished["xp_earned"] == 10
    assert await trainer.finish_session(
        session_id=session_id, user_id=user_id, revision=999
    ) == finished

    pool = await get_pool()
    async with pool.acquire() as connection:
        assert await connection.fetchval(
            "SELECT xp_total FROM diagnostic_progress_profiles WHERE user_id=$1", user_id
        ) == 10
        assert await connection.fetchval(
            "SELECT count(*) FROM diagnostic_trainer_answers WHERE session_id=$1", session_id
        ) == 1


@pytest.mark.asyncio
async def test_wrong_answer_spends_one_life_once_and_concurrent_retry_is_safe(database):
    user_id = 9_810_000_000 + uuid4().int % 100_000_000
    session_id, _ = await _start(user_id)
    key = "answer-1"
    fingerprint = trainer.answer_fingerprint(
        session_id=session_id, question_id="q0", answer="B", revision=1,
        idempotency_key=key,
    )

    async def submit():
        return await trainer.answer_question(
            session_id=session_id, user_id=user_id, question_id="q0", answer="B",
            revision=1, idempotency_key=key, fingerprint=fingerprint, is_correct=False,
            public_feedback={"correct_answer": "A", "explanation": "ok"},
        )

    first, retry = await asyncio.gather(submit(), submit())
    assert first == retry
    pool = await get_pool()
    async with pool.acquire() as connection:
        assert await connection.fetchval(
            "SELECT lives_remaining FROM diagnostic_progress_profiles WHERE user_id=$1", user_id
        ) == 4
        assert await connection.fetchval(
            "SELECT count(*) FROM diagnostic_trainer_answers WHERE session_id=$1", session_id
        ) == 1


@pytest.mark.asyncio
async def test_zero_lives_rejects_wrong_answer_without_inserting_row(database):
    user_id = 9_820_000_000 + uuid4().int % 100_000_000
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute(
            """
            INSERT INTO diagnostic_progress_profiles (user_id, lives_remaining)
            VALUES ($1, 0)
            """,
            user_id,
        )
    session_id, _ = await _start(user_id)
    key = "answer-1"
    fingerprint = trainer.answer_fingerprint(
        session_id=session_id, question_id="q0", answer="B", revision=1,
        idempotency_key=key,
    )
    with pytest.raises(ValueError, match="trainer_no_lives"):
        await trainer.answer_question(
            session_id=session_id, user_id=user_id, question_id="q0", answer="B",
            revision=1, idempotency_key=key, fingerprint=fingerprint, is_correct=False,
            public_feedback={"correct_answer": "A", "explanation": "ok"},
        )
    async with pool.acquire() as connection:
        assert await connection.fetchval(
            "SELECT count(*) FROM diagnostic_trainer_answers WHERE session_id=$1", session_id
        ) == 0


@pytest.mark.asyncio
async def test_user_erasure_cascades_trainer_rows(database):
    from diagnostic.admin.repository import delete_diagnostic_user

    user_id = 9_830_000_000 + uuid4().int % 100_000_000
    session_id, _ = await _start(user_id)
    await delete_diagnostic_user(user_id, "a" * 64, "b" * 32)
    pool = await get_pool()
    async with pool.acquire() as connection:
        assert await connection.fetchval(
            "SELECT count(*) FROM diagnostic_trainer_sessions WHERE session_id=$1", session_id
        ) == 0
        assert await connection.fetchval(
            "SELECT count(*) FROM diagnostic_trainer_answers WHERE session_id=$1", session_id
        ) == 0


@pytest.mark.asyncio
async def test_mistakes_are_seeded_from_owned_private_snapshot_and_sanitized(database):
    user_id = 9_840_000_000 + uuid4().int % 100_000_000
    attempt_id = f"attempt-{uuid4()}"
    await _source_attempt(user_id, attempt_id, snapshot={
        "review_snapshot": [
            {"question_id": "q1", "is_correct": False, "user_value": "B", "expected_value": "A"},
            {"question_id": "q2", "is_correct": True, "user_value": "A", "expected_value": "A"},
        ],
        "public_review_snapshot": [{"question_id": "q1", "is_correct": False}],
    })

    ids = await trainer.seed_and_list_mistakes(
        user_id=user_id, diagnostic_id="math-10", source_attempt_id=attempt_id,
        content_version="a" * 64,
    )
    assert ids == ["q1"]
    pool = await get_pool()
    async with pool.acquire() as connection:
        row = await connection.fetchrow(
            "SELECT source_attempt_id, source_content_version, resolved_at FROM diagnostic_mistakes WHERE user_id=$1 AND question_id='q1'",
            user_id,
        )
    assert row["source_attempt_id"] == attempt_id
    assert row["source_content_version"] == "a" * 64
    assert row["resolved_at"] is None

    with pytest.raises(ValueError, match="trainer_mistakes_source_not_found"):
        await trainer.seed_and_list_mistakes(
            user_id=user_id + 1, diagnostic_id="math-10", source_attempt_id=attempt_id,
            content_version="a" * 64,
        )


@pytest.mark.asyncio
async def test_mistake_replay_wrong_and_correct_are_idempotent_without_life_loss(database):
    user_id = 9_850_000_000 + uuid4().int % 100_000_000
    attempt_id = f"attempt-{uuid4()}"
    await _source_attempt(user_id, attempt_id, snapshot={
        "review_snapshot": [{"question_id": "q1", "is_correct": False, "user_value": "B", "expected_value": "A"}],
    })
    await trainer.seed_and_list_mistakes(
        user_id=user_id, diagnostic_id="math-10", source_attempt_id=attempt_id,
        content_version="a" * 64,
    )
    session_id = f"trainer_{uuid4().hex}"
    await trainer.start_session(
        session_id=session_id, user_id=user_id, diagnostic_id="math-10",
        content_version="a" * 64, mode="mistakes", source_attempt_id=attempt_id,
        selected_question_ids=["q1"],
    )
    key = "mistake-answer"
    fingerprint = trainer.answer_fingerprint(
        session_id=session_id, question_id="q1", answer="B", revision=1,
        idempotency_key=key,
    )
    wrong = await trainer.answer_question(
        session_id=session_id, user_id=user_id, question_id="q1", answer="B",
        revision=1, idempotency_key=key, fingerprint=fingerprint, is_correct=False,
        public_feedback={"correct_answer": "A", "explanation": "retry"},
    )
    assert wrong["life_delta"] == 0
    assert wrong["lives_remaining"] == 5
    assert await trainer.answer_question(
        session_id=session_id, user_id=user_id, question_id="q1", answer="B",
        revision=1, idempotency_key=key, fingerprint=fingerprint, is_correct=False,
        public_feedback={"correct_answer": "A", "explanation": "retry"},
    ) == wrong
    await trainer.finish_session(session_id=session_id, user_id=user_id, revision=2)

    pool = await get_pool()
    second_session = f"trainer_{uuid4().hex}"
    await trainer.start_session(
        session_id=second_session, user_id=user_id, diagnostic_id="math-10",
        content_version="a" * 64, mode="mistakes", source_attempt_id=attempt_id,
        selected_question_ids=["q1"],
    )
    correct_key = "mistake-correct"
    correct_fingerprint = trainer.answer_fingerprint(
        session_id=second_session, question_id="q1", answer="A", revision=1,
        idempotency_key=correct_key,
    )
    correct = await trainer.answer_question(
        session_id=second_session, user_id=user_id, question_id="q1", answer="A",
        revision=1, idempotency_key=correct_key, fingerprint=correct_fingerprint,
        is_correct=True, public_feedback={"correct_answer": "A", "explanation": "ok"},
    )
    assert correct["life_delta"] == 0
    assert correct["xp_delta"] == 0
    async with pool.acquire() as connection:
        assert await connection.fetchval(
            "SELECT xp_total FROM diagnostic_progress_profiles WHERE user_id=$1", user_id
        ) == 0
    async with pool.acquire() as connection:
        assert await connection.fetchval(
            "SELECT resolved_at IS NOT NULL FROM diagnostic_mistakes WHERE user_id=$1 AND question_id='q1'",
            user_id,
        ) is True


@pytest.mark.asyncio
async def test_new_source_reopens_resolved_mistake_but_same_source_does_not(database):
    user_id = 9_860_000_000 + uuid4().int % 100_000_000
    first_attempt = f"attempt-{uuid4()}"
    second_attempt = f"attempt-{uuid4()}"
    snapshot = {
        "review_snapshot": [{
            "question_id": "q1", "is_correct": False,
            "user_value": "B", "expected_value": "A",
        }],
    }
    await _source_attempt(user_id, first_attempt, snapshot=snapshot)
    assert await trainer.seed_and_list_mistakes(
        user_id=user_id, diagnostic_id="math-10", source_attempt_id=first_attempt,
        content_version="a" * 64,
    ) == ["q1"]
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute(
            "UPDATE diagnostic_mistakes SET resolved_at=now() WHERE user_id=$1 AND question_id='q1'",
            user_id,
        )

    assert await trainer.seed_and_list_mistakes(
        user_id=user_id, diagnostic_id="math-10", source_attempt_id=first_attempt,
        content_version="a" * 64,
    ) == []
    await _source_attempt(user_id, second_attempt, snapshot=snapshot)
    assert await trainer.seed_and_list_mistakes(
        user_id=user_id, diagnostic_id="math-10", source_attempt_id=second_attempt,
        content_version="a" * 64,
    ) == ["q1"]


@pytest.mark.asyncio
async def test_start_resumes_normal_session_without_mutating_selection(database):
    user_id = 9_870_000_000 + uuid4().int % 100_000_000
    first_id, (first, _) = await _start(user_id, count=2)

    resumed, _ = await trainer.start_session(
        session_id=f"trainer_{uuid4().hex}", user_id=user_id,
        diagnostic_id="math-10", content_version="a" * 64, mode="normal",
        selected_question_ids=["different-question"],
    )

    assert resumed["trainer_session_id"] == first_id
    assert resumed == first


@pytest.mark.asyncio
async def test_completed_session_is_not_resumed(database):
    user_id = 9_880_000_000 + uuid4().int % 100_000_000
    first_id, _ = await _start(user_id)
    key = "complete-answer"
    fingerprint = trainer.answer_fingerprint(
        session_id=first_id, question_id="q0", answer="A", revision=1,
        idempotency_key=key,
    )
    await trainer.answer_question(
        session_id=first_id, user_id=user_id, question_id="q0", answer="A",
        revision=1, idempotency_key=key, fingerprint=fingerprint, is_correct=True,
        public_feedback={"correct_answer": "A", "explanation": "ok"},
    )
    await trainer.finish_session(session_id=first_id, user_id=user_id, revision=2)

    second_id, (second, _) = await _start(user_id)

    assert second_id != first_id
    assert second["status"] == "active"


@pytest.mark.asyncio
async def test_concurrent_matching_starts_create_one_resumable_session(database):
    user_id = 9_890_000_000 + uuid4().int % 100_000_000

    async def start(index: int):
        return await trainer.start_session(
            session_id=f"trainer_{uuid4().hex}", user_id=user_id,
            diagnostic_id="math-10", content_version="a" * 64, mode="normal",
            selected_question_ids=[f"q{index}"],
        )

    first, second = await asyncio.gather(start(0), start(1))
    assert first[0] == second[0]
    pool = await get_pool()
    async with pool.acquire() as connection:
        assert await connection.fetchval(
            """
            SELECT count(*) FROM diagnostic_trainer_sessions
             WHERE user_id=$1 AND diagnostic_id='math-10'
               AND content_version=$2 AND mode='normal'
               AND status IN ('active', 'exhausted')
            """,
            user_id, "a" * 64,
        ) == 1


@pytest.mark.asyncio
async def test_matching_mistake_start_resumes_without_reseeding(database):
    user_id = 9_895_000_000 + uuid4().int % 100_000_000
    attempt_id = f"attempt-{uuid4()}"
    await _source_attempt(user_id, attempt_id, snapshot={
        "review_snapshot": [{
            "question_id": "q1", "is_correct": False,
            "user_value": "B", "expected_value": "A",
        }],
    })
    await trainer.seed_and_list_mistakes(
        user_id=user_id, diagnostic_id="math-10", source_attempt_id=attempt_id,
        content_version="a" * 64,
    )
    first, _ = await trainer.start_session(
        session_id=f"trainer_{uuid4().hex}", user_id=user_id,
        diagnostic_id="math-10", content_version="a" * 64, mode="mistakes",
        source_attempt_id=attempt_id, selected_question_ids=["q1"],
    )
    second, _ = await trainer.start_session(
        session_id=f"trainer_{uuid4().hex}", user_id=user_id,
        diagnostic_id="math-10", content_version="a" * 64, mode="mistakes",
        source_attempt_id=attempt_id, selected_question_ids=["q2"],
    )
    assert second["trainer_session_id"] == first["trainer_session_id"]
