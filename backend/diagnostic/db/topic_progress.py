"""Transactional persistence for per-user topic mastery on the topic path.

One row per (user, diagnostic, content version, topic). ``correct_question_ids``
is the set of that topic's questions the student has answered correctly at least
once; ``done_at`` is stamped when the set first covers the whole topic. Because
the content version is part of the key, a catalog change starts fresh progress
rather than mixing question sets.

Writes are additive and idempotent: recording the same correct answer twice is a
set union that changes nothing, and ``done_at`` is stamped once. The recording
helper runs inside the trainer answer transaction, which already holds the
per-user advisory lock and the erase guard.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from diagnostic.db.core import get_pool
from diagnostic.topic_path import TopicProgress


def _json_list(value: Any) -> list[str]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return []
    return [item for item in value or () if isinstance(item, str)]


async def record_topic_correct(
    connection,
    *,
    user_id: int,
    diagnostic_id: str,
    content_version: str,
    topic: str,
    question_id: str,
    topic_question_ids: Sequence[str],
) -> None:
    """Add one mastered question to its topic and close the topic when full.

    The caller owns the transaction and the per-user advisory lock.
    """
    if not topic:
        return
    row = await connection.fetchrow(
        """
        INSERT INTO diagnostic_topic_progress (
            user_id, diagnostic_id, content_version, topic, correct_question_ids
        ) VALUES ($1,$2,$3,$4, to_jsonb(ARRAY[$5]::text[]))
        ON CONFLICT (user_id, diagnostic_id, content_version, topic) DO UPDATE
           SET correct_question_ids = CASE
                   WHEN diagnostic_topic_progress.correct_question_ids @> to_jsonb($5::text)
                   THEN diagnostic_topic_progress.correct_question_ids
                   ELSE diagnostic_topic_progress.correct_question_ids || to_jsonb($5::text)
               END,
               updated_at=now()
        RETURNING correct_question_ids
        """,
        user_id,
        diagnostic_id,
        content_version,
        topic,
        question_id,
    )
    mastered = set(_json_list(row["correct_question_ids"]))
    topic_ids = set(topic_question_ids)
    if topic_ids and topic_ids.issubset(mastered):
        await connection.execute(
            """
            UPDATE diagnostic_topic_progress
               SET done_at=now(), updated_at=now()
             WHERE user_id=$1 AND diagnostic_id=$2 AND content_version=$3
               AND topic=$4 AND done_at IS NULL
            """,
            user_id,
            diagnostic_id,
            content_version,
            topic,
        )


async def seed_topic_progress(
    connection,
    *,
    user_id: int,
    diagnostic_id: str,
    content_version: str,
    correct_by_topic: Mapping[str, Sequence[str]],
) -> None:
    """Union each topic's correctly-answered question ids into its mastery set.

    Used to seed the path from a completed diagnostic. The caller owns the
    transaction, the per-user advisory lock and the erase guard. ``done_at`` is
    left unstamped on purpose: a quick diagnostic covers only part of a topic, so
    the path derives ``done`` from ``mastered >= total`` against the full catalog
    topic instead of a premature stamp.
    """
    for topic, question_ids in correct_by_topic.items():
        ids = [qid for qid in question_ids if isinstance(qid, str) and qid]
        if not topic or not ids:
            continue
        await connection.execute(
            """
            INSERT INTO diagnostic_topic_progress (
                user_id, diagnostic_id, content_version, topic, correct_question_ids
            ) VALUES ($1,$2,$3,$4, to_jsonb($5::text[]))
            ON CONFLICT (user_id, diagnostic_id, content_version, topic) DO UPDATE
               SET correct_question_ids = (
                       SELECT to_jsonb(array_agg(DISTINCT value))
                         FROM (
                             SELECT jsonb_array_elements_text(
                                        diagnostic_topic_progress.correct_question_ids
                                    ) AS value
                             UNION
                             SELECT unnest($5::text[]) AS value
                         ) AS merged
                   ),
                   updated_at=now()
            """,
            user_id,
            diagnostic_id,
            content_version,
            topic,
            ids,
        )


def _progress_map(rows: Sequence[Mapping[str, Any]]) -> dict[str, TopicProgress]:
    result: dict[str, TopicProgress] = {}
    for row in rows:
        done_at = row["done_at"]
        result[row["topic"]] = TopicProgress(
            correct_ids=frozenset(_json_list(row["correct_question_ids"])),
            done_at=done_at.isoformat() if hasattr(done_at, "isoformat") else done_at,
        )
    return result


async def read_progress_map(
    connection, *, user_id: int, diagnostic_id: str, content_version: str
) -> dict[str, TopicProgress]:
    """Per-topic mastery for the path builder, read on an open connection."""
    rows = await connection.fetch(
        """
        SELECT topic, correct_question_ids, done_at
          FROM diagnostic_topic_progress
         WHERE user_id=$1 AND diagnostic_id=$2 AND content_version=$3
        """,
        user_id,
        diagnostic_id,
        content_version,
    )
    return _progress_map(rows)


async def get_progress_map(
    user_id: int, diagnostic_id: str, content_version: str
) -> dict[str, TopicProgress]:
    """Pool-level read of per-topic mastery."""
    pool = await get_pool()
    async with pool.acquire() as connection:
        return await read_progress_map(
            connection,
            user_id=user_id,
            diagnostic_id=diagnostic_id,
            content_version=content_version,
        )


async def latest_completed_diagnostic(user_id: int) -> str | None:
    """The diagnostic of the student's most recent completed attempt, if any.

    This mirrors how the daily plan resolves the student's active subject, so the
    today endpoint and the plan agree on which diagnostic the path belongs to.
    """
    pool = await get_pool()
    async with pool.acquire() as connection:
        return await connection.fetchval(
            """
            SELECT diagnostic_id
              FROM diagnostic_attempts
             WHERE user_id=$1 AND status='completed'
             ORDER BY completed_at DESC, updated_at DESC
             LIMIT 1
            """,
            user_id,
        )
