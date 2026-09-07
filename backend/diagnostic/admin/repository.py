"""Parameterized, diagnostic-only administration queries."""

from __future__ import annotations

from diagnostic.db.core import get_pool
from diagnostic.db import content, funnel


def _bounded(limit: int, offset: int) -> tuple[int, int]:
    return max(1, min(int(limit), 100)), max(0, int(offset))


async def list_users(*, offset: int = 0, user_id: int | None = None) -> list:
    pool = await get_pool()
    async with pool.acquire() as connection:
        return await connection.fetch(
            """
            SELECT e.user_id, e.opened_at, e.last_opened_at,
                   e.notifications_enabled, e.onboarding_started_at,
                   COALESCE(p.completion_count, 0) AS completed,
                   COALESCE(p.streak_days, 0) AS streak_days,
                   p.streak_last_date, COALESCE(p.lives_remaining, 5) AS lives_remaining,
                   p.lives_refill_at, COALESCE(p.xp_total, 0) AS xp_total,
                   a.started, a.subject, a.result_subject, a.correct_count, a.question_count, a.errors
              FROM diagnostic_engagements e
              LEFT JOIN diagnostic_progress_profiles p USING (user_id)
              LEFT JOIN LATERAL (
                  SELECT count(*) AS started,
                         (array_agg(subject ORDER BY updated_at DESC))[1] AS subject,
                         (array_agg(subject ORDER BY completed_at DESC NULLS LAST)
                             FILTER (WHERE status='completed'))[1] AS result_subject,
                         (array_agg(correct_count ORDER BY completed_at DESC NULLS LAST)
                             FILTER (WHERE status='completed'))[1] AS correct_count,
                         (array_agg(question_count ORDER BY completed_at DESC NULLS LAST)
                             FILTER (WHERE status='completed'))[1] AS question_count,
                         count(*) FILTER (WHERE pdf_status='abandoned') AS errors
                    FROM diagnostic_attempts WHERE user_id=e.user_id
              ) a ON true
             WHERE ($1::bigint IS NULL OR e.user_id=$1)
             ORDER BY e.last_opened_at DESC, e.user_id
             LIMIT 50 OFFSET $2
            """, user_id, max(0, offset),
        )


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


async def get_funnel(*, days: int, exam: str | None, subject: str | None) -> dict:
    return await funnel.funnel_report(days=days, exam=exam, subject=subject)


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
            funnel_events = await connection.execute(
                "DELETE FROM diagnostic_funnel_events WHERE subject_hash=$1",
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
        "funnel_events": _delete_count(funnel_events),
    }
