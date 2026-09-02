"""Transactional persistence for the daily plan.

One plan per user per school-local day. The plan is built once, under the same
per-user advisory lock the trainer takes, and every later request returns the
stored row so progress is never lost to a rebuild.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
import json
from typing import Any

from diagnostic.daily_plan import DailyPlan, MistakeState, PlanSource, next_review
from diagnostic.db import gameplay
from diagnostic.db.attempts import _raise_if_erased
from diagnostic.db.core import get_pool


@dataclass(frozen=True)
class PlanInputs:
    """Everything the pure builder needs, read inside the locked transaction."""

    plan_date: date
    source: PlanSource | None
    mistakes: tuple[MistakeState, ...]


PlanBuilder = Callable[[PlanInputs], DailyPlan | None]


def _json_list(value: Any) -> list[str]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return []
    return [item for item in value or () if isinstance(item, str)]


def _json_object(value: Any) -> dict[str, str]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    if not isinstance(value, Mapping):
        return {}
    return {
        key: item for key, item in value.items()
        if isinstance(key, str) and isinstance(item, str)
    }


def serialize_plan(row: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Shape one stored plan row for the API and bot layers."""
    if row is None:
        return None
    question_ids = _json_list(row["question_ids"])
    completed = [
        question_id for question_id in _json_list(row["completed_question_ids"])
        if question_id in set(question_ids)
    ]
    plan_date = row["plan_date"]
    return {
        "plan_date": plan_date.isoformat() if hasattr(plan_date, "isoformat") else str(plan_date),
        "diagnostic_id": row["diagnostic_id"],
        "content_version": row["content_version"],
        "source_attempt_id": row["source_attempt_id"],
        "question_ids": question_ids,
        "reasons": _json_object(row["reasons"]),
        "completed_question_ids": completed,
        "total": len(question_ids),
        "completed": len(completed),
    }


_PLAN_COLUMNS = """
plan_date, diagnostic_id, content_version, source_attempt_id,
question_ids, reasons, completed_question_ids
""".strip()


async def _read_plan(connection, user_id: int, plan_date: date, *, lock: bool = False):
    return await connection.fetchrow(
        f"""
        SELECT {_PLAN_COLUMNS} FROM diagnostic_daily_plans
         WHERE user_id=$1 AND plan_date=$2
        {"FOR UPDATE" if lock else ""}
        """,
        user_id,
        plan_date,
    )


async def _read_inputs(connection, user_id: int, plan_date: date) -> PlanInputs:
    attempt = await connection.fetchrow(
        """
        SELECT attempt_id, diagnostic_id, growth_topics, answers
          FROM diagnostic_attempts
         WHERE user_id=$1 AND status='completed'
         ORDER BY completed_at DESC, updated_at DESC
         LIMIT 1
        """,
        user_id,
    )
    if attempt is None:
        return PlanInputs(plan_date=plan_date, source=None, mistakes=())
    answers = attempt["answers"]
    if isinstance(answers, str):
        try:
            answers = json.loads(answers)
        except ValueError:
            answers = {}
    source = PlanSource(
        attempt_id=attempt["attempt_id"],
        diagnostic_id=attempt["diagnostic_id"],
        growth_topics=tuple(attempt["growth_topics"] or ()),
        answered_question_ids=frozenset(answers or {}),
    )
    rows = await connection.fetch(
        """
        SELECT question_id, review_count, next_review_on
          FROM diagnostic_mistakes
         WHERE user_id=$1 AND diagnostic_id=$2
         ORDER BY created_at, question_id
        """,
        user_id,
        source.diagnostic_id,
    )
    mistakes = tuple(
        MistakeState(
            question_id=row["question_id"],
            review_count=int(row["review_count"] or 0),
            next_review_on=row["next_review_on"],
        )
        for row in rows
    )
    return PlanInputs(plan_date=plan_date, source=source, mistakes=mistakes)


async def _sync_daily_goal(connection, user_id: int, plan_date: date, plan: Mapping[str, Any]) -> None:
    """The plan owns the daily goal on the day it exists."""
    await connection.execute(
        """
        UPDATE diagnostic_progress_profiles
           SET daily_goal_target=GREATEST(LEAST($3::int, 100), 1),
               daily_goal_progress=LEAST($4::int, GREATEST(LEAST($3::int, 100), 1)),
               daily_goal_date=$2::date,
               updated_at=now()
         WHERE user_id=$1
        """,
        user_id,
        plan_date,
        plan["total"],
        plan["completed"],
    )


async def ensure_plan(
    *, user_id: int, plan_date: date, build: PlanBuilder
) -> dict[str, Any] | None:
    """Return today's plan, building it once under the per-user advisory lock.

    ``build`` is a pure callable: it receives the locked snapshot and returns the
    plan for today. A stored plan is reused as-is unless its diagnostic or content
    version no longer matches what the builder resolves, which self-heals a plan
    that outlived a catalog change.
    """
    pool = await get_pool()
    async with pool.acquire() as connection:
        async with connection.transaction():
            await connection.execute("SELECT pg_advisory_xact_lock($1)", user_id)
            await _raise_if_erased(connection, user_id)
            await gameplay.get_reconciled_profile(connection, user_id)
            existing = await _read_plan(connection, user_id, plan_date, lock=True)
            built = build(await _read_inputs(connection, user_id, plan_date))
            stored = serialize_plan(existing)
            if stored is not None and (
                built is None or (
                    stored["diagnostic_id"] == built.diagnostic_id
                    and stored["content_version"] == built.content_version
                )
            ):
                await _sync_daily_goal(connection, user_id, plan_date, stored)
                return stored
            if built is None:
                return None
            row = await connection.fetchrow(
                f"""
                INSERT INTO diagnostic_daily_plans (
                    user_id, plan_date, diagnostic_id, content_version,
                    source_attempt_id, question_ids, reasons
                ) VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7::jsonb)
                ON CONFLICT (user_id, plan_date) DO UPDATE SET
                    diagnostic_id=EXCLUDED.diagnostic_id,
                    content_version=EXCLUDED.content_version,
                    source_attempt_id=EXCLUDED.source_attempt_id,
                    question_ids=EXCLUDED.question_ids,
                    reasons=EXCLUDED.reasons,
                    completed_question_ids='[]'::jsonb,
                    created_at=now()
                RETURNING {_PLAN_COLUMNS}
                """,
                user_id,
                plan_date,
                built.diagnostic_id,
                built.content_version,
                built.source_attempt_id,
                built.question_ids,
                built.reasons,
            )
            plan = serialize_plan(row)
            if plan is not None:
                await _sync_daily_goal(connection, user_id, plan_date, plan)
            return plan


async def get_plan(user_id: int, plan_date: date) -> dict[str, Any] | None:
    """Read today's plan without building one."""
    pool = await get_pool()
    async with pool.acquire() as connection:
        return serialize_plan(await _read_plan(connection, user_id, plan_date))


async def record_plan_answer(
    connection, *, user_id: int, plan_date: date, diagnostic_id: str,
    question_id: str, is_correct: bool,
) -> None:
    """Mark one plan question answered and reschedule its mistake review.

    The caller owns the transaction and the user advisory lock.
    """
    row = await connection.fetchrow(
        f"""
        UPDATE diagnostic_daily_plans
           SET completed_question_ids = CASE
                   WHEN completed_question_ids @> to_jsonb($3::text)
                   THEN completed_question_ids
                   ELSE completed_question_ids || to_jsonb($3::text)
               END
         WHERE user_id=$1 AND plan_date=$2
           AND question_ids @> to_jsonb($3::text)
        RETURNING {_PLAN_COLUMNS}
        """,
        user_id,
        plan_date,
        question_id,
    )
    if row is None:
        return
    review_count = await connection.fetchval(
        """
        SELECT review_count FROM diagnostic_mistakes
         WHERE user_id=$1 AND diagnostic_id=$2 AND question_id=$3
        """,
        user_id, diagnostic_id, question_id,
    )
    if review_count is not None:
        count, due_on = next_review(
            int(review_count), correct=is_correct, today=plan_date
        )
        await connection.execute(
            """
            UPDATE diagnostic_mistakes
               SET review_count=$4, next_review_on=$5,
                   resolved_at=CASE WHEN $6 THEN COALESCE(resolved_at, now()) ELSE NULL END
             WHERE user_id=$1 AND diagnostic_id=$2 AND question_id=$3
            """,
            user_id, diagnostic_id, question_id, count, due_on, is_correct,
        )
    plan = serialize_plan(row)
    if plan is not None:
        await _sync_daily_goal(connection, user_id, plan_date, plan)
