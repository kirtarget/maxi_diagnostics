"""Parameterized, diagnostic-only administration queries."""

from __future__ import annotations

from diagnostic.db.core import get_pool
from diagnostic.db import content


def _bounded(limit: int, offset: int) -> tuple[int, int]:
    return max(1, min(int(limit), 100)), max(0, int(offset))


def _delete_count(status: str) -> int:
    try:
        return int(status.rsplit(" ", 1)[1])
    except (IndexError, ValueError):
        return 0


async def list_content_drafts() -> list:
    return await content.list_drafts()


async def get_content_draft(diagnostic_id: str):
    return await content.get_draft(diagnostic_id)


async def create_content_draft(**kwargs):
    return await content.create_draft(**kwargs)


async def save_content_draft(**kwargs):
    return await content.save_draft(**kwargs)


async def record_content_action(**kwargs):
    return await content.record_action(**kwargs)


async def get_summary() -> dict[str, int]:
    pool = await get_pool()
    async with pool.acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT
              (SELECT count(*) FROM diagnostic_attempts) AS attempts,
              (SELECT count(*) FROM diagnostic_attempts WHERE status='completed') AS completed,
              (SELECT count(*) FROM diagnostic_attempts
                WHERE status='completed' AND pdf_status IN ('pending','failed','sending')) AS pending_pdfs,
              (SELECT count(*) FROM diagnostic_notifications
                WHERE due_at <= now() AND status IN ('pending','failed','sending')) AS due_notifications
            """
        )
    return {key: int(row[key]) for key in ("attempts", "completed", "pending_pdfs", "due_notifications")}


async def list_attempts(*, limit: int, offset: int) -> tuple[int, list]:
    limit, offset = _bounded(limit, offset)
    pool = await get_pool()
    async with pool.acquire() as connection:
        total = await connection.fetchval("SELECT count(*) FROM diagnostic_attempts")
        rows = await connection.fetch(
            """
            SELECT attempt_id, user_id, diagnostic_id, exam, subject, mode, status,
                   question_index, question_count, correct_count, score, max_score,
                   score_unit, unassessed_part, strong_topics, growth_topics,
                   pdf_status, pdf_attempts, pdf_delivered_at, pdf_message_id,
                   completed_at, result_viewed_at, updated_at
              FROM diagnostic_attempts
             ORDER BY updated_at DESC, attempt_id
             LIMIT $1 OFFSET $2
            """,
            limit,
            offset,
        )
    return int(total), list(rows)


async def list_delivery_issues(*, limit: int, offset: int) -> tuple[int, list]:
    limit, offset = _bounded(limit, offset)
    pool = await get_pool()
    async with pool.acquire() as connection:
        total = await connection.fetchval(
            "SELECT count(*) FROM diagnostic_attempts WHERE pdf_status IN ('failed','abandoned')"
        )
        rows = await connection.fetch(
            """
            SELECT attempt_id, user_id, diagnostic_id, exam, subject, mode,
                   pdf_status, pdf_attempts, completed_at, updated_at
              FROM diagnostic_attempts
             WHERE pdf_status IN ('failed','abandoned')
             ORDER BY updated_at DESC, attempt_id
             LIMIT $1 OFFSET $2
            """,
            limit,
            offset,
        )
    return int(total), list(rows)


async def list_notification_issues(*, limit: int, offset: int) -> tuple[int, list]:
    limit, offset = _bounded(limit, offset)
    pool = await get_pool()
    async with pool.acquire() as connection:
        total = await connection.fetchval(
            "SELECT count(*) FROM diagnostic_notifications WHERE status IN ('failed','abandoned')"
        )
        rows = await connection.fetch(
            """
            SELECT id, user_id, attempt_id, kind, due_at, status, attempts,
                   sent_at, updated_at
              FROM diagnostic_notifications
             WHERE status IN ('failed','abandoned')
             ORDER BY updated_at DESC, id
             LIMIT $1 OFFSET $2
            """,
            limit,
            offset,
        )
    return int(total), list(rows)


async def list_messages() -> list:
    pool = await get_pool()
    async with pool.acquire() as connection:
        return list(
            await connection.fetch(
                "SELECT key, text, description, updated_at FROM message_templates ORDER BY key"
            )
        )


async def update_message(key: str, text: str):
    pool = await get_pool()
    async with pool.acquire() as connection:
        return await connection.fetchrow(
            """
            UPDATE message_templates
               SET text=$2, updated_at=now()
             WHERE key=$1
            RETURNING key, text, description, updated_at
            """,
            key,
            text,
        )


async def delete_diagnostic_user(
    user_id: int, session_subject_key: str, new_session_generation: str
) -> dict[str, int]:
    """Erase diagnostic rows and leave a durable writer/worker barrier."""
    pool = await get_pool()
    async with pool.acquire() as connection:
        async with connection.transaction():
            await connection.execute("SELECT pg_advisory_xact_lock($1)", user_id)
            await connection.execute(
                "DELETE FROM diagnostic_erased_users WHERE user_id <> $1 AND erased_at <= now() - interval '15 minutes'",
                user_id,
            )
            await connection.execute(
                """
                INSERT INTO diagnostic_erased_users (user_id, erased_at)
                VALUES ($1, now())
                ON CONFLICT (user_id) DO UPDATE SET erased_at=EXCLUDED.erased_at
                """,
                user_id,
            )
            await connection.execute(
                """
                INSERT INTO diagnostic_session_generations
                    (subject_key, generation, updated_at)
                VALUES ($1, $2, now())
                ON CONFLICT (subject_key) DO UPDATE
                    SET generation=EXCLUDED.generation, updated_at=now()
                """,
                session_subject_key,
                new_session_generation,
            )
            notifications = await connection.execute(
                "DELETE FROM diagnostic_notifications WHERE user_id=$1", user_id
            )
            attempts = await connection.execute(
                "DELETE FROM diagnostic_attempts WHERE user_id=$1", user_id
            )
            engagements = await connection.execute(
                "DELETE FROM diagnostic_engagements WHERE user_id=$1", user_id
            )
            await connection.execute(
                "DELETE FROM diagnostic_progress_events WHERE user_id=$1", user_id
            )
            offer_events = await connection.execute(
                "DELETE FROM diagnostic_offer_events WHERE subject_hash=$1",
                session_subject_key,
            )
            await connection.execute(
                # Trainer sessions reference the profile with ON DELETE CASCADE.
                # Deleting the profile here therefore erases trainer answers and
                # sessions in the same transaction without leaving private payloads.
                "DELETE FROM diagnostic_progress_profiles WHERE user_id=$1", user_id
            )
    return {
        "notifications": _delete_count(notifications),
        "attempts": _delete_count(attempts),
        "engagements": _delete_count(engagements),
        "offer_events": _delete_count(offer_events),
    }
