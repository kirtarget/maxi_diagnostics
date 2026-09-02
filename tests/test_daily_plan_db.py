"""PostgreSQL-backed daily plan behaviour. Skipped without TEST_DATABASE_URL."""

from datetime import date, timedelta
import os
from uuid import uuid4

import pytest
import pytest_asyncio

from diagnostic.daily_plan import DailyPlan, PlanQuestion
from diagnostic.db import daily_plan, trainer
from diagnostic.db.core import close_db, get_pool, init_db


PLAN_DATE = date(2026, 9, 2)
VERSION = "a" * 64


@pytest_asyncio.fixture
async def database():
    if not os.getenv("TEST_DATABASE_URL"):
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")
    await init_db(os.environ["TEST_DATABASE_URL"])
    yield
    await close_db()


def new_user_id() -> int:
    return 9_600_000_000 + uuid4().int % 100_000_000


async def seed_completed_attempt(user_id: int, attempt_id: str) -> None:
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute(
            "INSERT INTO diagnostic_progress_profiles (user_id) VALUES ($1)"
            " ON CONFLICT DO NOTHING",
            user_id,
        )
        await connection.execute(
            """
            INSERT INTO diagnostic_attempts (
                attempt_id, user_id, diagnostic_id, content_version,
                exam, subject, mode, status, question_count, completed_at,
                growth_topics, answers
            ) VALUES ($1,$2,'math-10',$3,'ege','math','full','completed',4,now(),
                      $4::text[], $5::jsonb)
            """,
            attempt_id, user_id, VERSION, ["Геометрия"],
            {"q0": "a", "q1": "b"},
        )


def plan_of(*question_ids: str) -> DailyPlan:
    return DailyPlan(
        plan_date=PLAN_DATE,
        diagnostic_id="math-10",
        content_version=VERSION,
        source_attempt_id=None,
        questions=tuple(
            PlanQuestion(question_id=question_id, topic="Геометрия", reason="growth_topic")
            for question_id in question_ids
        ),
    )


@pytest.mark.asyncio
async def test_plan_is_built_once_per_day_and_keeps_progress(database):
    user_id = new_user_id()
    attempt_id = f"attempt_{uuid4().hex[:16]}"
    await seed_completed_attempt(user_id, attempt_id)
    calls: list[int] = []

    def build(inputs):
        calls.append(len(inputs.mistakes))
        return plan_of("q0", "q1", "q2")

    first = await daily_plan.ensure_plan(user_id=user_id, plan_date=PLAN_DATE, build=build)
    assert first["question_ids"] == ["q0", "q1", "q2"]
    assert first["total"] == 3 and first["completed"] == 0

    pool = await get_pool()
    async with pool.acquire() as connection:
        async with connection.transaction():
            await daily_plan.record_plan_answer(
                connection, user_id=user_id, plan_date=PLAN_DATE,
                diagnostic_id="math-10", question_id="q1", is_correct=True,
            )

    second = await daily_plan.ensure_plan(
        user_id=user_id, plan_date=PLAN_DATE, build=lambda inputs: plan_of("zzz")
    )
    assert second["question_ids"] == ["q0", "q1", "q2"]
    assert second["completed_question_ids"] == ["q1"]
    assert second["completed"] == 1
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_plan_is_rebuilt_when_the_content_version_moves_on(database):
    user_id = new_user_id()
    await seed_completed_attempt(user_id, f"attempt_{uuid4().hex[:16]}")
    await daily_plan.ensure_plan(
        user_id=user_id, plan_date=PLAN_DATE, build=lambda inputs: plan_of("q0")
    )

    rebuilt = await daily_plan.ensure_plan(
        user_id=user_id, plan_date=PLAN_DATE,
        build=lambda inputs: DailyPlan(
            plan_date=PLAN_DATE, diagnostic_id="math-10", content_version="b" * 64,
            source_attempt_id=None,
            questions=(PlanQuestion("q2", "Геометрия", "growth_topic"),),
        ),
    )
    assert rebuilt["question_ids"] == ["q2"]
    assert rebuilt["content_version"] == "b" * 64


@pytest.mark.asyncio
async def test_no_plan_without_a_completed_diagnostic(database):
    user_id = new_user_id()
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute(
            "INSERT INTO diagnostic_progress_profiles (user_id) VALUES ($1)", user_id
        )

    calls: list[object] = []

    def build(inputs):
        calls.append(inputs.source)
        return None

    assert await daily_plan.ensure_plan(
        user_id=user_id, plan_date=PLAN_DATE, build=build
    ) is None
    assert calls == [None]


@pytest.mark.asyncio
async def test_daily_goal_follows_the_plan_size_and_progress(database):
    user_id = new_user_id()
    await seed_completed_attempt(user_id, f"attempt_{uuid4().hex[:16]}")
    await daily_plan.ensure_plan(
        user_id=user_id, plan_date=PLAN_DATE, build=lambda inputs: plan_of("q0", "q1", "q2")
    )

    pool = await get_pool()
    async with pool.acquire() as connection:
        goal = await connection.fetchrow(
            "SELECT daily_goal_target, daily_goal_progress, daily_goal_date"
            "  FROM diagnostic_progress_profiles WHERE user_id=$1",
            user_id,
        )
        assert (goal["daily_goal_target"], goal["daily_goal_progress"]) == (3, 0)
        assert goal["daily_goal_date"] == PLAN_DATE

        async with connection.transaction():
            for question_id in ("q0", "q1"):
                await daily_plan.record_plan_answer(
                    connection, user_id=user_id, plan_date=PLAN_DATE,
                    diagnostic_id="math-10", question_id=question_id, is_correct=True,
                )
        goal = await connection.fetchrow(
            "SELECT daily_goal_target, daily_goal_progress"
            "  FROM diagnostic_progress_profiles WHERE user_id=$1",
            user_id,
        )
    assert (goal["daily_goal_target"], goal["daily_goal_progress"]) == (3, 2)


@pytest.mark.asyncio
async def test_plan_answers_advance_and_reset_the_spaced_review_interval(database):
    user_id = new_user_id()
    attempt_id = f"attempt_{uuid4().hex[:16]}"
    await seed_completed_attempt(user_id, attempt_id)
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.executemany(
            """
            INSERT INTO diagnostic_mistakes (
                user_id, diagnostic_id, question_id, source_attempt_id,
                source_content_version, review_count, next_review_on
            ) VALUES ($1,'math-10',$2,$3,$4,0,$5)
            """,
            [
                (user_id, "q0", attempt_id, VERSION, PLAN_DATE),
                (user_id, "q1", attempt_id, VERSION, PLAN_DATE),
            ],
        )
    await daily_plan.ensure_plan(
        user_id=user_id, plan_date=PLAN_DATE, build=lambda inputs: plan_of("q0", "q1")
    )

    async with pool.acquire() as connection:
        async with connection.transaction():
            await daily_plan.record_plan_answer(
                connection, user_id=user_id, plan_date=PLAN_DATE,
                diagnostic_id="math-10", question_id="q0", is_correct=True,
            )
            await daily_plan.record_plan_answer(
                connection, user_id=user_id, plan_date=PLAN_DATE,
                diagnostic_id="math-10", question_id="q1", is_correct=False,
            )
        rows = {
            row["question_id"]: row
            for row in await connection.fetch(
                "SELECT question_id, review_count, next_review_on, resolved_at"
                "  FROM diagnostic_mistakes WHERE user_id=$1",
                user_id,
            )
        }
    assert rows["q0"]["review_count"] == 1
    assert rows["q0"]["next_review_on"] == PLAN_DATE + timedelta(days=3)
    assert rows["q0"]["resolved_at"] is not None
    assert rows["q1"]["review_count"] == 0
    assert rows["q1"]["next_review_on"] == PLAN_DATE + timedelta(days=1)
    assert rows["q1"]["resolved_at"] is None


@pytest.mark.asyncio
async def test_plan_trainer_session_spends_lives_and_marks_the_plan(database):
    user_id = new_user_id()
    await seed_completed_attempt(user_id, f"attempt_{uuid4().hex[:16]}")
    today = trainer.plan_date_for("Europe/Moscow")
    await daily_plan.ensure_plan(
        user_id=user_id, plan_date=today,
        build=lambda inputs: DailyPlan(
            plan_date=today, diagnostic_id="math-10", content_version=VERSION,
            source_attempt_id=None,
            questions=(
                PlanQuestion("q0", "Геометрия", "growth_topic"),
                PlanQuestion("q1", "Геометрия", "growth_topic"),
            ),
        ),
    )
    session_id = f"trainer_{uuid4().hex}"
    session, _ = await trainer.start_session(
        session_id=session_id, user_id=user_id, diagnostic_id="math-10",
        content_version=VERSION, mode="plan", selected_question_ids=["q0", "q1"],
    )
    assert session["mode"] == "plan"

    key = "plan-answer-1"
    result = await trainer.answer_question(
        session_id=session_id, user_id=user_id, question_id="q0", answer="A",
        revision=1, idempotency_key=key,
        fingerprint=trainer.answer_fingerprint(
            session_id=session_id, question_id="q0", answer="A", revision=1,
            idempotency_key=key,
        ),
        is_correct=True, public_feedback={}, timezone_name="Europe/Moscow",
    )
    assert result["xp_delta"] == 10

    stored = await daily_plan.get_plan(user_id, today)
    assert stored["completed_question_ids"] == ["q0"]
    assert stored["completed"] == 1

    pool = await get_pool()
    async with pool.acquire() as connection:
        goal = await connection.fetchrow(
            "SELECT daily_goal_target, daily_goal_progress"
            "  FROM diagnostic_progress_profiles WHERE user_id=$1",
            user_id,
        )
    assert (goal["daily_goal_target"], goal["daily_goal_progress"]) == (2, 1)


@pytest.mark.asyncio
async def test_streak_save_is_queued_once_per_local_day(database):
    from diagnostic.db import attempts

    user_id = new_user_id()
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute(
            """
            INSERT INTO diagnostic_progress_profiles (user_id, streak_days, streak_last_date)
            VALUES ($1, 3, (now() AT TIME ZONE 'Europe/Moscow')::date - 1)
            """,
            user_id,
        )

    await attempts.schedule_streak_save_notifications(timezone_name="Europe/Moscow")
    await attempts.schedule_streak_save_notifications(timezone_name="Europe/Moscow")

    async with pool.acquire() as connection:
        rows = await connection.fetch(
            "SELECT kind, status FROM diagnostic_notifications"
            " WHERE user_id=$1 AND kind='streak_save'",
            user_id,
        )
    assert [row["status"] for row in rows] == ["pending"]


@pytest.mark.asyncio
async def test_streak_save_skips_an_active_streak_and_a_short_one(database):
    from diagnostic.db import attempts

    active = new_user_id()
    short = new_user_id()
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute(
            """
            INSERT INTO diagnostic_progress_profiles (user_id, streak_days, streak_last_date)
            VALUES ($1, 5, (now() AT TIME ZONE 'Europe/Moscow')::date),
                   ($2, 1, (now() AT TIME ZONE 'Europe/Moscow')::date - 1)
            """,
            active, short,
        )

    await attempts.schedule_streak_save_notifications(timezone_name="Europe/Moscow")

    async with pool.acquire() as connection:
        count = await connection.fetchval(
            "SELECT count(*) FROM diagnostic_notifications"
            " WHERE user_id = ANY($1::bigint[]) AND kind='streak_save'",
            [active, short],
        )
    assert count == 0
