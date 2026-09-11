"""Transactional persistence for passed weekly checkpoints.

One row per passed (user, diagnostic, content version, unit). A row is written once
and never rewritten, so replaying a record keeps the original pass. The content
version is part of the key, so a catalog change begins a fresh set of units.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from diagnostic.db.attempts import _raise_if_erased
from diagnostic.db.core import get_pool
from diagnostic.topic_checkpoint import PassedCheckpoint


def _passed_map(rows: Sequence[Mapping[str, Any]]) -> dict[int, PassedCheckpoint]:
    result: dict[int, PassedCheckpoint] = {}
    for row in rows:
        unit_index = int(row["unit_index"])
        result[unit_index] = PassedCheckpoint(
            unit_index=unit_index,
            passed_at=row["passed_at"],
            mastered_count=int(row["correct_count"]),
            question_total=int(row["question_count"]),
        )
    return result


async def read_passed_map(
    connection, *, user_id: int, diagnostic_id: str, content_version: str
) -> dict[int, PassedCheckpoint]:
    rows = await connection.fetch(
        """
        SELECT unit_index, passed_at, correct_count, question_count
          FROM diagnostic_topic_checkpoints
         WHERE user_id=$1 AND diagnostic_id=$2 AND content_version=$3
        """,
        user_id,
        diagnostic_id,
        content_version,
    )
    return _passed_map(rows)


async def get_passed_map(
    user_id: int, diagnostic_id: str, content_version: str
) -> dict[int, PassedCheckpoint]:
    """Pool-level read of the user's passed checkpoints for one diagnostic."""
    pool = await get_pool()
    async with pool.acquire() as connection:
        return await read_passed_map(
            connection,
            user_id=user_id,
            diagnostic_id=diagnostic_id,
            content_version=content_version,
        )


async def record_pass(
    *,
    user_id: int,
    diagnostic_id: str,
    content_version: str,
    unit_index: int,
    session_id: str | None,
    correct_count: int,
    question_count: int,
) -> PassedCheckpoint:
    """Persist one passed checkpoint. A replay keeps the first immutable pass."""
    pool = await get_pool()
    async with pool.acquire() as connection:
        async with connection.transaction():
            await connection.execute("SELECT pg_advisory_xact_lock($1)", user_id)
            await _raise_if_erased(connection, user_id)
            await connection.execute(
                """
                INSERT INTO diagnostic_topic_checkpoints (
                    user_id, diagnostic_id, content_version, unit_index,
                    session_id, correct_count, question_count
                ) VALUES ($1,$2,$3,$4,$5,$6,$7)
                ON CONFLICT (user_id, diagnostic_id, content_version, unit_index)
                    DO NOTHING
                """,
                user_id,
                diagnostic_id,
                content_version,
                unit_index,
                session_id,
                correct_count,
                question_count,
            )
            row = await connection.fetchrow(
                """
                SELECT unit_index, passed_at, correct_count, question_count
                  FROM diagnostic_topic_checkpoints
                 WHERE user_id=$1 AND diagnostic_id=$2 AND content_version=$3
                   AND unit_index=$4
                """,
                user_id,
                diagnostic_id,
                content_version,
                unit_index,
            )
    return _passed_map([row])[int(row["unit_index"])]
