"""Attempt persistence and reliable diagnostic delivery state machines."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Literal

from diagnostic.db.core import get_pool
from diagnostic.db import gameplay
from diagnostic.session_identity import new_session_generation, session_subject_key


_ATTEMPT_PUBLIC_COLUMNS = """
attempt_id, user_id, diagnostic_id, content_version,
exam, subject, mode, status, question_index, question_count, progress_revision,
answers, correct_count, score, max_score, score_unit, unassessed_part,
strong_topics, growth_topics, forecast, result_snapshot, started_at, updated_at,
completed_at, result_viewed_at, pdf_status, pdf_attempts, pdf_last_error,
pdf_locked_at, pdf_delivered_at, pdf_message_id
""".strip()
_ATTEMPT_DELIVERY_COLUMNS = (
    f"{_ATTEMPT_PUBLIC_COLUMNS}, report_snapshot, report_asset_bundle_id, "
    "report_assets, pdf_document"
)
_SANITIZED_REVIEW_SNAPSHOT = """
CASE
    WHEN jsonb_typeof(report_snapshot->'public_review_snapshot') = 'array'
    THEN jsonb_build_object('review_snapshot', report_snapshot->'public_review_snapshot')
    WHEN jsonb_typeof(report_snapshot->'review_snapshot') = 'array'
         AND NOT EXISTS (
             SELECT 1
               FROM jsonb_array_elements(report_snapshot->'review_snapshot') AS review(item)
              WHERE jsonb_typeof(review.item) != 'object'
                 OR EXISTS (
                     SELECT 1
                       FROM jsonb_object_keys(review.item) AS field(key)
                      WHERE field.key NOT IN (
                          'question_id', 'number', 'type', 'topic', 'title', 'prompt',
                          'asset', 'assets', 'is_correct', 'user_answer',
                          'expected_answer', 'guidance', 'guidance_kind'
                      )
                 )
         )
    THEN jsonb_build_object('review_snapshot', report_snapshot->'review_snapshot')
    ELSE '{}'::jsonb
END
""".strip()


@dataclass(frozen=True)
class AttemptProgress:
    attempt_id: str
    user_id: int
    diagnostic_id: str
    content_version: str
    exam: str
    subject: str
    mode: Literal["quick", "full"]
    question_index: int
    question_count: int
    answers: dict[str, Any]
    progress_revision: int = 1
    supersedes_attempt_id: str | None = None


@dataclass(frozen=True)
class AttemptCompletion:
    attempt_id: str
    user_id: int
    diagnostic_id: str
    content_version: str
    exam: str
    subject: str
    mode: Literal["quick", "full"]
    question_count: int
    progress_revision: int
    answers: dict[str, Any]
    correct_count: int
    score: int
    max_score: int
    score_unit: str
    unassessed_part: str | None
    strong_topics: list[str] = field(default_factory=list)
    growth_topics: list[str] = field(default_factory=list)
    forecast: dict[str, Any] = field(default_factory=dict)
    result_snapshot: dict[str, Any] = field(default_factory=dict)
    report_snapshot: dict[str, Any] = field(default_factory=dict)
    report_asset_bundle_id: str | None = None
    report_assets: bytes | None = None
    pdf_document: bytes | None = None
    supersedes_attempt_id: str | None = None
    activity_timezone: str = "Europe/Moscow"


async def _raise_if_erased(connection, user_id: int) -> None:
    await connection.execute(
        "DELETE FROM diagnostic_erased_users WHERE user_id=$1 AND erased_at <= now() - interval '15 minutes'",
        user_id,
    )
    erased = await connection.fetchval(
        "SELECT EXISTS (SELECT 1 FROM diagnostic_erased_users WHERE user_id=$1)",
        user_id,
    )
    if erased:
        raise ValueError("diagnostic_user_erased")


async def get_or_create_session_generation(
    subject_key: str, proposed_generation: str
) -> str:
    pool = await get_pool()
    async with pool.acquire() as connection:
        async with connection.transaction():
            await connection.execute(
                """
                INSERT INTO diagnostic_session_generations (subject_key, generation)
                VALUES ($1, $2)
                ON CONFLICT (subject_key) DO NOTHING
                """,
                subject_key,
                proposed_generation,
            )
            generation = await connection.fetchval(
                "SELECT generation FROM diagnostic_session_generations WHERE subject_key=$1",
                subject_key,
            )
    if generation is None:
        raise RuntimeError("session_generation_unavailable")
    return generation


async def get_session_generation(subject_key: str) -> str | None:
    pool = await get_pool()
    async with pool.acquire() as connection:
        return await connection.fetchval(
            "SELECT generation FROM diagnostic_session_generations WHERE subject_key=$1",
            subject_key,
        )


async def _cancel_quick_to_full(connection, user_id: int, diagnostic_id: str) -> None:
    await connection.execute(
        """
        UPDATE diagnostic_notifications AS notification
           SET status='cancelled', locked_at=NULL, updated_at=now()
          FROM diagnostic_attempts AS source
         WHERE notification.attempt_id=source.attempt_id
           AND notification.user_id=$1
           AND notification.kind='quick_to_full'
           AND notification.status IN ('pending', 'failed', 'sending')
           AND source.user_id=$1 AND source.diagnostic_id=$2 AND source.mode='quick'
        """,
        user_id,
        diagnostic_id,
    )


async def _record_completion_progress(
    connection, attempt_id, user_id, mode, activity_timezone
) -> None:
    ledger = await connection.fetchrow(
        """
        INSERT INTO diagnostic_completion_ledger (attempt_id, user_id)
        VALUES ($1, $2)
        ON CONFLICT (attempt_id) DO NOTHING
        RETURNING attempt_id
        """,
        attempt_id,
        user_id,
    )
    await gameplay.record_diagnostic_completion(
        connection,
        user_id=user_id,
        attempt_id=attempt_id,
        mode=mode,
        timezone_name=activity_timezone,
    )
    if ledger is not None:
        await connection.execute(
            """
            INSERT INTO diagnostic_progress_profiles (user_id, completion_count, achievement_keys)
            VALUES ($1, 1, jsonb_build_array('first_diagnostic_completed'))
            ON CONFLICT (user_id) DO UPDATE
            SET completion_count = diagnostic_progress_profiles.completion_count + 1,
                achievement_keys = CASE
                    WHEN diagnostic_progress_profiles.achievement_keys @> jsonb_build_array('first_diagnostic_completed')
                    THEN diagnostic_progress_profiles.achievement_keys
                    ELSE diagnostic_progress_profiles.achievement_keys || jsonb_build_array('first_diagnostic_completed')
                END,
                updated_at = now()
            """,
            user_id,
        )


async def mark_opened(user_id: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as connection:
        async with connection.transaction():
            await connection.execute("SELECT pg_advisory_xact_lock($1)", user_id)
            await _raise_if_erased(connection, user_id)
            created = await connection.fetchrow(
                """
                INSERT INTO diagnostic_engagements (user_id, opened_at, last_opened_at)
                VALUES ($1, now(), now())
                ON CONFLICT (user_id) DO NOTHING
                RETURNING user_id
                """,
                user_id,
            )
            if created is None:
                touched = await connection.fetchrow(
                    """
                    UPDATE diagnostic_engagements SET last_opened_at=now()
                     WHERE user_id=$1
                       AND last_opened_at <= now() - interval '30 seconds'
                    RETURNING user_id
                    """,
                    user_id,
                )
            else:
                touched = created
            if touched is not None:
                await connection.execute(
                    """
                    INSERT INTO diagnostic_notifications (dedupe_key, user_id, kind, due_at)
                    SELECT 'not_started:' || $1::bigint::text || ':' || to_char(now(), 'YYYYMM'),
                           $1, 'not_started', now() + interval '3 hours'
                     WHERE NOT EXISTS (
                         SELECT 1 FROM diagnostic_attempts WHERE user_id=$1
                     )
                    ON CONFLICT (dedupe_key) DO NOTHING
                    """,
                    user_id,
                )
            return created is not None


async def store_report_asset_bundle(bundle_id: str, payload: bytes) -> None:
    if len(bundle_id) != 64 or not payload or len(payload) > 25 * 1024 * 1024:
        raise ValueError("report_assets_invalid")
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute(
            """
            INSERT INTO diagnostic_report_asset_bundles (bundle_id, payload)
            VALUES ($1, $2)
            ON CONFLICT (bundle_id) DO NOTHING
            """,
            bundle_id,
            payload,
        )


async def get_report_asset_bundle(bundle_id: str) -> bytes | None:
    pool = await get_pool()
    async with pool.acquire() as connection:
        return await connection.fetchval(
            "SELECT payload FROM diagnostic_report_asset_bundles WHERE bundle_id=$1",
            bundle_id,
        )


async def upsert_progress(progress: AttemptProgress):
    """Persist only the owning user's resumable in-progress attempt."""
    pool = await get_pool()
    async with pool.acquire() as connection:
        async with connection.transaction():
            await connection.execute(
                "SELECT pg_advisory_xact_lock($1)", progress.user_id
            )
            await _raise_if_erased(connection, progress.user_id)
            existing = await connection.fetchrow(
                f"SELECT {_ATTEMPT_PUBLIC_COLUMNS} FROM diagnostic_attempts WHERE attempt_id=$1",
                progress.attempt_id,
            )
            if existing is not None and existing["user_id"] != progress.user_id:
                raise ValueError("diagnostic_attempt_conflict")
            if existing is not None and (
                existing["diagnostic_id"] != progress.diagnostic_id
                or existing["content_version"] != progress.content_version
                or existing["exam"] != progress.exam
                or existing["subject"] != progress.subject
                or existing["mode"] != progress.mode
                or existing["question_count"] != progress.question_count
            ):
                raise ValueError("diagnostic_attempt_conflict")
            if existing is not None:
                if existing["status"] == "completed":
                    return await connection.fetchrow(
                        f"SELECT {_ATTEMPT_PUBLIC_COLUMNS}, false AS started_transition "
                        "FROM diagnostic_attempts WHERE attempt_id=$1 AND user_id=$2",
                        progress.attempt_id,
                        progress.user_id,
                    )
                if existing["status"] != "in_progress":
                    raise ValueError("diagnostic_attempt_conflict")
                stored_revision = existing["progress_revision"]
                if progress.progress_revision == stored_revision:
                    if (
                        existing["question_index"] == progress.question_index
                        and existing["answers"] == progress.answers
                    ):
                        return await connection.fetchrow(
                            f"SELECT {_ATTEMPT_PUBLIC_COLUMNS}, false AS started_transition "
                            "FROM diagnostic_attempts WHERE attempt_id=$1 AND user_id=$2",
                            progress.attempt_id,
                            progress.user_id,
                        )
                    raise ValueError("diagnostic_progress_stale")
                if progress.progress_revision != stored_revision + 1:
                    raise ValueError("diagnostic_progress_stale")
            if existing is None:
                if progress.progress_revision != 1:
                    raise ValueError("diagnostic_progress_stale")
                active_ids = {
                    row["attempt_id"] for row in await connection.fetch(
                        "SELECT attempt_id FROM diagnostic_attempts WHERE user_id=$1 AND status='in_progress'",
                        progress.user_id,
                    )
                }
                if active_ids:
                    if active_ids != {progress.supersedes_attempt_id}:
                        raise ValueError("diagnostic_attempt_conflict")
                elif progress.supersedes_attempt_id is not None:
                    latest_attempt_id = await connection.fetchval(
                        """SELECT attempt_id FROM diagnostic_attempts
                            WHERE user_id=$1
                            ORDER BY started_at DESC, attempt_id DESC LIMIT 1""",
                        progress.user_id,
                    )
                    if latest_attempt_id != progress.supersedes_attempt_id:
                        raise ValueError("diagnostic_attempt_conflict")
                recent_start_count = await connection.fetchval(
                    """
                    SELECT count(*) FROM diagnostic_attempts
                     WHERE user_id=$1 AND started_at >= now() - interval '1 hour'
                    """,
                    progress.user_id,
                )
                if int(recent_start_count or 0) >= 10:
                    raise ValueError("diagnostic_rate_limited")
                superseded = await connection.fetch(
                    """
                    UPDATE diagnostic_attempts
                       SET status='superseded', updated_at=now()
                     WHERE user_id=$1 AND status='in_progress'
                    RETURNING attempt_id
                    """,
                    progress.user_id,
                )
                if superseded:
                    await connection.execute(
                        """
                        UPDATE diagnostic_notifications
                           SET status='cancelled', locked_at=NULL, updated_at=now()
                         WHERE user_id=$1 AND kind='incomplete'
                           AND status IN ('pending', 'failed', 'sending')
                        """,
                        progress.user_id,
                    )
            row = await connection.fetchrow(
                f"""
                INSERT INTO diagnostic_attempts (
                    attempt_id, user_id, diagnostic_id,
                    content_version, exam, subject, mode, question_index, question_count, answers,
                    progress_revision, status
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,'in_progress')
                ON CONFLICT (attempt_id) DO UPDATE SET
                    question_index=EXCLUDED.question_index,
                    answers=EXCLUDED.answers,
                    progress_revision=EXCLUDED.progress_revision,
                    updated_at=now()
                WHERE diagnostic_attempts.user_id=EXCLUDED.user_id
                  AND diagnostic_attempts.status='in_progress'
                  AND EXCLUDED.progress_revision = diagnostic_attempts.progress_revision + 1
                RETURNING {_ATTEMPT_PUBLIC_COLUMNS}, $12::boolean AS started_transition
                """,
                progress.attempt_id, progress.user_id, progress.diagnostic_id,
                progress.content_version, progress.exam, progress.subject, progress.mode,
                progress.question_index, progress.question_count, progress.answers,
                progress.progress_revision,
                existing is None,
            )
            if row is None:
                row = await connection.fetchrow(
                    f"SELECT {_ATTEMPT_PUBLIC_COLUMNS}, false AS started_transition "
                    "FROM diagnostic_attempts WHERE attempt_id=$1 AND user_id=$2",
                    progress.attempt_id,
                    progress.user_id,
                )
            if row is None:
                raise ValueError("diagnostic_attempt_conflict")
            if row["status"] != "in_progress":
                return row
            if progress.mode == "full":
                await _cancel_quick_to_full(
                    connection, progress.user_id, progress.diagnostic_id
                )
            await connection.execute(
                """
                UPDATE diagnostic_notifications
                   SET status='cancelled', locked_at=NULL, updated_at=now()
                 WHERE user_id=$1 AND kind='not_started'
                   AND status IN ('pending', 'failed', 'sending')
                """,
                progress.user_id,
            )
            await connection.execute(
                """
                INSERT INTO diagnostic_notifications (dedupe_key, user_id, attempt_id, kind, due_at, payload)
                VALUES ('incomplete:' || $1, $2, $1, 'incomplete', now() + interval '2 hours',
                        jsonb_build_object('mode', $3::text))
                ON CONFLICT (dedupe_key) DO UPDATE SET
                    due_at=EXCLUDED.due_at,
                    status=CASE WHEN diagnostic_notifications.status='sent' THEN 'sent' ELSE 'pending' END,
                    payload=EXCLUDED.payload, locked_at=NULL, last_error=NULL, updated_at=now()
                """,
                progress.attempt_id,
                progress.user_id,
                progress.mode,
            )
            return row


async def complete_attempt(completion: AttemptCompletion):
    """Complete once; repeated calls return the original immutable result."""
    pool = await get_pool()
    async with pool.acquire() as connection:
        async with connection.transaction():
            await connection.execute(
                "SELECT pg_advisory_xact_lock($1)", completion.user_id
            )
            await _raise_if_erased(connection, completion.user_id)
            existing = await connection.fetchrow(
                f"SELECT {_ATTEMPT_PUBLIC_COLUMNS} FROM diagnostic_attempts WHERE attempt_id=$1",
                completion.attempt_id,
            )
            if existing is not None:
                if existing["user_id"] != completion.user_id:
                    raise ValueError("diagnostic_attempt_conflict")
                if existing["status"] == "completed":
                    return existing
                if existing["status"] != "in_progress":
                    raise ValueError("diagnostic_attempt_conflict")
                if completion.progress_revision != existing["progress_revision"] + 1:
                    raise ValueError("diagnostic_progress_stale")
                if (
                    existing["diagnostic_id"] != completion.diagnostic_id
                    or existing["content_version"] != completion.content_version
                    or existing["mode"] != completion.mode
                    or existing["question_count"] != completion.question_count
                    or existing["exam"] != completion.exam
                    or existing["subject"] != completion.subject
                ):
                    raise ValueError("diagnostic_attempt_conflict")
            elif completion.progress_revision != 1:
                raise ValueError("diagnostic_progress_stale")
            if existing is None:
                active_ids = {
                    row["attempt_id"] for row in await connection.fetch(
                        "SELECT attempt_id FROM diagnostic_attempts WHERE user_id=$1 AND status='in_progress'",
                        completion.user_id,
                    )
                }
                if active_ids:
                    if active_ids != {completion.supersedes_attempt_id}:
                        raise ValueError("diagnostic_attempt_conflict")
                elif completion.supersedes_attempt_id is not None:
                    latest_attempt_id = await connection.fetchval(
                        """SELECT attempt_id FROM diagnostic_attempts
                            WHERE user_id=$1
                            ORDER BY started_at DESC, attempt_id DESC LIMIT 1""",
                        completion.user_id,
                    )
                    if latest_attempt_id != completion.supersedes_attempt_id:
                        raise ValueError("diagnostic_attempt_conflict")
                recent_start_count = await connection.fetchval(
                    """
                    SELECT count(*) FROM diagnostic_attempts
                     WHERE user_id=$1 AND started_at >= now() - interval '1 hour'
                    """,
                    completion.user_id,
                )
                if int(recent_start_count or 0) >= 10:
                    raise ValueError("diagnostic_rate_limited")
            recent_count = await connection.fetchval(
                """
                SELECT count(*) FROM diagnostic_attempts
                 WHERE user_id=$1 AND status='completed'
                   AND completed_at >= now() - interval '1 hour'
                """,
                completion.user_id,
            )
            if int(recent_count or 0) >= 20:
                raise ValueError("diagnostic_rate_limited")
            if existing is None:
                superseded = await connection.fetch(
                    """
                    UPDATE diagnostic_attempts
                       SET status='superseded', updated_at=now()
                     WHERE user_id=$1 AND status='in_progress'
                    RETURNING attempt_id
                    """,
                    completion.user_id,
                )
                if superseded:
                    await connection.execute(
                        """
                        UPDATE diagnostic_notifications
                           SET status='cancelled', locked_at=NULL, updated_at=now()
                         WHERE user_id=$1 AND kind='incomplete'
                           AND status IN ('pending', 'failed', 'sending')
                        """,
                        completion.user_id,
                    )
            row = await connection.fetchrow(
                f"""
                INSERT INTO diagnostic_attempts (
                    attempt_id, user_id, diagnostic_id, content_version, exam,
                    subject, mode, status, question_index, question_count, answers,
                    progress_revision, correct_count, score, max_score, score_unit,
                    unassessed_part, strong_topics, growth_topics,
                    forecast, result_snapshot, report_snapshot, report_asset_bundle_id,
                    report_assets, pdf_document,
                    completed_at, updated_at, pdf_status
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,'completed',$8,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23,now(),now(),'pending')
                ON CONFLICT (attempt_id) DO UPDATE SET
                    diagnostic_id=EXCLUDED.diagnostic_id,
                    content_version=EXCLUDED.content_version,
                    exam=EXCLUDED.exam,
                    subject=EXCLUDED.subject,
                    mode=EXCLUDED.mode,
                    status='completed',
                    question_index=EXCLUDED.question_index,
                    question_count=EXCLUDED.question_count,
                    answers=EXCLUDED.answers,
                    progress_revision=EXCLUDED.progress_revision,
                    correct_count=EXCLUDED.correct_count,
                    score=EXCLUDED.score,
                    max_score=EXCLUDED.max_score,
                    score_unit=EXCLUDED.score_unit,
                    unassessed_part=EXCLUDED.unassessed_part,
                    strong_topics=EXCLUDED.strong_topics,
                    growth_topics=EXCLUDED.growth_topics,
                    forecast=EXCLUDED.forecast,
                    result_snapshot=EXCLUDED.result_snapshot,
                    report_snapshot=EXCLUDED.report_snapshot,
                    report_asset_bundle_id=EXCLUDED.report_asset_bundle_id,
                    report_assets=EXCLUDED.report_assets,
                    pdf_document=EXCLUDED.pdf_document,
                    completed_at=now(), updated_at=now()
                WHERE diagnostic_attempts.user_id=EXCLUDED.user_id
                  AND diagnostic_attempts.status = 'in_progress'
                  AND EXCLUDED.progress_revision = diagnostic_attempts.progress_revision + 1
                RETURNING {_ATTEMPT_PUBLIC_COLUMNS}, $24::boolean AS completed_transition,
                              $25::boolean AS started_transition
                """,
                completion.attempt_id, completion.user_id, completion.diagnostic_id,
                completion.content_version, completion.exam, completion.subject,
                completion.mode, completion.question_count,
                completion.answers, completion.progress_revision, completion.correct_count,
                completion.score, completion.max_score, completion.score_unit,
                completion.unassessed_part, completion.strong_topics, completion.growth_topics,
                completion.forecast, completion.result_snapshot, completion.report_snapshot,
                completion.report_asset_bundle_id,
                completion.report_assets,
                completion.pdf_document,
                True,
                existing is None,
            )
            if row is None:
                row = await connection.fetchrow(
                    f"SELECT {_ATTEMPT_PUBLIC_COLUMNS} FROM diagnostic_attempts WHERE attempt_id=$1 AND user_id=$2",
                    completion.attempt_id,
                    completion.user_id,
                )
            if row is None:
                raise ValueError("diagnostic_attempt_conflict")
            if row["status"] == "completed":
                await _record_completion_progress(
                    connection,
                    completion.attempt_id,
                    completion.user_id,
                    row["mode"],
                    completion.activity_timezone,
                )
            stored_mode = row["mode"]
            stored_subject = row["subject"]
            if stored_mode == "full":
                await _cancel_quick_to_full(
                    connection, completion.user_id, completion.diagnostic_id
                )
            await connection.execute(
                """
                UPDATE diagnostic_notifications
                   SET status='cancelled', locked_at=NULL, updated_at=now()
                 WHERE user_id=$1 AND (kind='not_started' OR attempt_id=$2)
                   AND kind IN ('not_started', 'incomplete')
                   AND status IN ('pending', 'failed', 'sending')
                """,
                completion.user_id,
                completion.attempt_id,
            )
            notifications = [
                ("result_unviewed", timedelta(hours=3)),
                ("day_followup", timedelta(days=1)),
                ("month_retest", timedelta(days=30)),
            ]
            if stored_mode == "quick":
                notifications.append(("quick_to_full", timedelta(days=3)))
            for kind, delay in notifications:
                await connection.execute(
                    """
                    INSERT INTO diagnostic_notifications (dedupe_key, user_id, attempt_id, kind, due_at, payload)
                    VALUES ($1,$2,$3,$4,now() + $5::interval,$6)
                    ON CONFLICT (dedupe_key) DO NOTHING
                    """,
                    f"{kind}:{completion.attempt_id}", completion.user_id, completion.attempt_id,
                    kind, delay, {"mode": stored_mode, "subject": stored_subject},
                )
            return row


async def get_attempt(attempt_id: str, user_id: int | None = None):
    pool = await get_pool()
    async with pool.acquire() as connection:
        if user_id is None:
            return await connection.fetchrow(
                f"SELECT {_ATTEMPT_PUBLIC_COLUMNS} FROM diagnostic_attempts WHERE attempt_id=$1",
                attempt_id,
            )
        return await connection.fetchrow(
            f"SELECT {_ATTEMPT_PUBLIC_COLUMNS} FROM diagnostic_attempts WHERE attempt_id=$1 AND user_id=$2",
            attempt_id,
            user_id,
        )


async def get_review_attempt(attempt_id: str, user_id: int):
    pool = await get_pool()
    async with pool.acquire() as connection:
        return await connection.fetchrow(
            """
            SELECT attempt_id, status, pdf_status, report_snapshot
              FROM diagnostic_attempts
             WHERE attempt_id=$1 AND user_id=$2
            """,
            attempt_id,
            user_id,
        )


async def get_resumable_attempt(user_id: int):
    pool = await get_pool()
    async with pool.acquire() as connection:
        return await connection.fetchrow(
            f"""
            SELECT {_ATTEMPT_PUBLIC_COLUMNS} FROM diagnostic_attempts
             WHERE user_id=$1 AND status='in_progress'
             ORDER BY updated_at DESC LIMIT 1
            """,
            user_id,
        )


async def get_latest_attempt_id(user_id: int) -> str | None:
    pool = await get_pool()
    async with pool.acquire() as connection:
        return await connection.fetchval(
            """
            SELECT attempt_id FROM diagnostic_attempts
             WHERE user_id=$1
             ORDER BY started_at DESC, attempt_id DESC LIMIT 1
            """,
            user_id,
        )


async def get_progress_profile(user_id: int):
    pool = await get_pool()
    async with pool.acquire() as connection:
        return await connection.fetchrow(
            """
            SELECT completion_count, achievement_keys
              FROM diagnostic_progress_profiles
             WHERE user_id=$1
            """,
            user_id,
        )


async def get_gameplay_profile(user_id: int):
    pool = await get_pool()
    async with pool.acquire() as connection:
        return await gameplay.get_gameplay_profile(connection, user_id)


async def list_completed_attempts(user_id: int) -> list:
    pool = await get_pool()
    async with pool.acquire() as connection:
        return await connection.fetch(
            f"""
            SELECT {_ATTEMPT_PUBLIC_COLUMNS} FROM diagnostic_attempts
             WHERE user_id=$1 AND status='completed'
             ORDER BY completed_at DESC, updated_at DESC LIMIT 20
            """,
            user_id,
        )


async def mark_result_viewed(attempt_id: str, user_id: int):
    pool = await get_pool()
    async with pool.acquire() as connection:
        async with connection.transaction():
            row = await connection.fetchrow(
                """
                WITH target AS (
                    SELECT attempt_id, result_viewed_at IS NULL AS viewed_transition
                      FROM diagnostic_attempts
                     WHERE attempt_id=$1 AND user_id=$2 AND status='completed'
                     FOR UPDATE
                )
                UPDATE diagnostic_attempts AS attempt
                   SET result_viewed_at=COALESCE(attempt.result_viewed_at, now())
                  FROM target
                 WHERE attempt.attempt_id=target.attempt_id
                RETURNING attempt.attempt_id, target.viewed_transition
                """,
                attempt_id,
                user_id,
            )
            if row is None:
                raise ValueError("diagnostic_attempt_conflict")
            if row["viewed_transition"]:
                await connection.execute(
                    """
                    UPDATE diagnostic_notifications
                       SET status='cancelled', locked_at=NULL, updated_at=now()
                     WHERE attempt_id=$1 AND user_id=$2 AND kind='result_unviewed'
                       AND status IN ('pending', 'failed', 'sending')
                    """,
                    attempt_id,
                    user_id,
                )
            current = await connection.fetchrow(
                f"SELECT {_ATTEMPT_PUBLIC_COLUMNS} FROM diagnostic_attempts WHERE attempt_id=$1 AND user_id=$2",
                attempt_id,
                user_id,
            )
            return dict(current) | {"viewed_transition": row["viewed_transition"]}


async def list_notifications(attempt_id: str) -> list:
    pool = await get_pool()
    async with pool.acquire() as connection:
        return await connection.fetch(
            "SELECT * FROM diagnostic_notifications WHERE attempt_id=$1 ORDER BY id", attempt_id
        )


async def claim_pending_pdf(attempt_id: str | None = None):
    pool = await get_pool()
    async with pool.acquire() as connection:
        async with connection.transaction():
            await connection.execute(
                f"""
                UPDATE diagnostic_attempts
                   SET pdf_status='abandoned', pdf_locked_at=NULL,
                       pdf_last_error='retry_limit_reached', pdf_document=NULL,
                       report_assets=NULL, answers='{{}}'::jsonb,
                       report_snapshot={_SANITIZED_REVIEW_SNAPSHOT}, report_asset_bundle_id=NULL,
                       updated_at=now()
                 WHERE status='completed' AND pdf_status='sending'
                   AND pdf_attempts >= 8
                   AND pdf_locked_at <= now() - interval '10 minutes'
                """
            )
            row = await connection.fetchrow(
                """
                SELECT attempt_id FROM diagnostic_attempts
                 WHERE status='completed' AND pdf_delivered_at IS NULL AND pdf_attempts < 8
                   AND NOT EXISTS (
                       SELECT 1 FROM diagnostic_erased_users erased
                        WHERE erased.user_id=diagnostic_attempts.user_id
                          AND erased.erased_at > now() - interval '15 minutes'
                   )
                   AND ($1::text IS NULL OR attempt_id=$1)
                   AND (pdf_status='pending'
                     OR (pdf_status='failed' AND updated_at <= now() - interval '5 minutes')
                     OR (pdf_status='sending' AND pdf_locked_at <= now() - interval '10 minutes'))
                 ORDER BY completed_at FOR UPDATE SKIP LOCKED LIMIT 1
                """,
                attempt_id,
            )
            if row is None:
                return None
            return await connection.fetchrow(
                f"""
                UPDATE diagnostic_attempts
                   SET pdf_status='sending', pdf_locked_at=now(), pdf_attempts=pdf_attempts+1,
                       updated_at=now()
                 WHERE attempt_id=$1 RETURNING {_ATTEMPT_DELIVERY_COLUMNS}
                """,
                row["attempt_id"],
            )


async def mark_pdf_delivered(
    attempt_id: str, lease: datetime, message_id: int | None
) -> bool:
    pool = await get_pool()
    async with pool.acquire() as connection:
        row = await connection.fetchrow(
            f"""
            UPDATE diagnostic_attempts
               SET pdf_status='sent', pdf_delivered_at=now(), pdf_message_id=$2,
                   pdf_locked_at=NULL, pdf_last_error=NULL, pdf_document=NULL,
                   report_assets=NULL, answers='{{}}'::jsonb,
                   report_snapshot={_SANITIZED_REVIEW_SNAPSHOT},
                   report_asset_bundle_id=NULL, updated_at=now()
             WHERE attempt_id=$1 AND pdf_status='sending' AND pdf_locked_at=$3
            RETURNING attempt_id
            """,
            attempt_id,
            message_id,
            lease,
        )
        return row is not None


async def pdf_delivery_is_sent(attempt_id: str, message_id: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as connection:
        return bool(await connection.fetchval(
            "SELECT pdf_status='sent' AND pdf_message_id=$2 FROM diagnostic_attempts WHERE attempt_id=$1",
            attempt_id,
            message_id,
        ))


async def purge_expired_erasure_tombstones() -> int:
    pool = await get_pool()
    async with pool.acquire() as connection:
        status = await connection.execute(
            "DELETE FROM diagnostic_erased_users WHERE erased_at <= now() - interval '15 minutes'"
        )
    return int(status.rsplit(" ", 1)[-1])


async def purge_retained_diagnostic_data(
    application_secret: str,
    diagnostic_retention_days: int,
    in_progress_retention_days: int,
    *,
    user_limit: int = 100,
) -> dict[str, int]:
    """Minimize stale drafts and expire old learner-linked diagnostic history."""
    if not 31 <= diagnostic_retention_days <= 3650:
        raise ValueError("invalid_diagnostic_retention_days")
    if not 1 <= in_progress_retention_days <= 365:
        raise ValueError("invalid_in_progress_retention_days")
    if not 1 <= user_limit <= 500:
        raise ValueError("invalid_retention_batch_limit")

    counts = {
        "superseded": 0,
        "deleted_attempts": 0,
        "deleted_engagements": 0,
        "deleted_bundles": 0,
    }
    pool = await get_pool()
    async with pool.acquire() as connection:
        async with connection.transaction():
            candidates = await connection.fetch(
                """
                SELECT DISTINCT user_id
                  FROM diagnostic_attempts
                 WHERE (status='in_progress'
                        AND updated_at <= now() - make_interval(days => $1))
                    OR (status='completed'
                        AND completed_at <= now() - make_interval(days => $2))
                    OR (status='superseded'
                        AND started_at <= now() - make_interval(days => $2))
                 ORDER BY user_id
                 LIMIT $3
                """,
                in_progress_retention_days,
                diagnostic_retention_days,
                user_limit,
            )
            for candidate in candidates:
                user_id = candidate["user_id"]
                await connection.execute("SELECT pg_advisory_xact_lock($1)", user_id)
                status = await connection.execute(
                    """
                    UPDATE diagnostic_attempts
                       SET status='superseded', answers='{}'::jsonb,
                           question_index=0, report_snapshot='{}'::jsonb,
                           report_assets=NULL, report_asset_bundle_id=NULL,
                           pdf_document=NULL, updated_at=now()
                     WHERE user_id=$1 AND status='in_progress'
                       AND updated_at <= now() - make_interval(days => $2)
                    """,
                    user_id,
                    in_progress_retention_days,
                )
                counts["superseded"] += int(status.rsplit(" ", 1)[-1])
                await connection.execute(
                    """
                    UPDATE diagnostic_notifications AS notification
                       SET status='cancelled', locked_at=NULL, updated_at=now()
                     WHERE notification.user_id=$1
                       AND notification.status IN ('pending', 'failed', 'sending')
                       AND EXISTS (
                           SELECT 1 FROM diagnostic_attempts AS attempt
                            WHERE attempt.attempt_id=notification.attempt_id
                              AND attempt.status='superseded'
                       )
                    """,
                    user_id,
                )
                status = await connection.execute(
                    """
                    DELETE FROM diagnostic_attempts
                     WHERE user_id=$1
                       AND ((status='completed' AND completed_at <= now() - make_interval(days => $2))
                         OR (status='superseded' AND started_at <= now() - make_interval(days => $2)))
                    """,
                    user_id,
                    diagnostic_retention_days,
                )
                counts["deleted_attempts"] += int(status.rsplit(" ", 1)[-1])
                has_attempts = await connection.fetchval(
                    "SELECT EXISTS (SELECT 1 FROM diagnostic_attempts WHERE user_id=$1)",
                    user_id,
                )
                if not has_attempts:
                    await connection.execute(
                        """
                        INSERT INTO diagnostic_session_generations
                            (subject_key, generation, updated_at)
                        VALUES ($1, $2, now())
                        ON CONFLICT (subject_key) DO UPDATE
                            SET generation=EXCLUDED.generation, updated_at=now()
                        """,
                        session_subject_key(application_secret, user_id),
                        new_session_generation(),
                    )

            status = await connection.execute(
                """
                DELETE FROM diagnostic_engagements AS engagement
                 WHERE engagement.last_opened_at <= now() - make_interval(days => $1)
                   AND NOT EXISTS (
                       SELECT 1 FROM diagnostic_attempts AS attempt
                        WHERE attempt.user_id=engagement.user_id
                   )
                   AND NOT EXISTS (
                       SELECT 1 FROM diagnostic_notifications AS notification
                        WHERE notification.user_id=engagement.user_id
                          AND notification.status IN ('pending', 'failed', 'sending')
                   )
                """,
                diagnostic_retention_days,
            )
            counts["deleted_engagements"] = int(status.rsplit(" ", 1)[-1])
            status = await connection.execute(
                """
                DELETE FROM diagnostic_report_asset_bundles AS bundle
                 WHERE bundle.created_at <= now() - make_interval(days => $1)
                   AND NOT EXISTS (
                       SELECT 1 FROM diagnostic_attempts AS attempt
                        WHERE attempt.report_asset_bundle_id=bundle.bundle_id
                   )
                """,
                diagnostic_retention_days,
            )
            counts["deleted_bundles"] = int(status.rsplit(" ", 1)[-1])
    return counts


async def pdf_claim_is_active(attempt_id: str, lease: datetime) -> bool:
    pool = await get_pool()
    async with pool.acquire() as connection:
        return bool(await connection.fetchval(
            """
            SELECT EXISTS (
                SELECT 1 FROM diagnostic_attempts attempt
                 WHERE attempt.attempt_id=$1
                   AND attempt.pdf_status='sending' AND attempt.pdf_locked_at=$2
                   AND NOT EXISTS (
                       SELECT 1 FROM diagnostic_erased_users erased
                        WHERE erased.user_id=attempt.user_id
                          AND erased.erased_at > now() - interval '15 minutes'
                   )
            )
            """,
            attempt_id,
            lease,
        ))


async def store_pdf_document(
    attempt_id: str, lease: datetime, document: bytes
) -> bool:
    if not document or len(document) > 25 * 1024 * 1024:
        raise ValueError("pdf_document_invalid")
    pool = await get_pool()
    async with pool.acquire() as connection:
        row = await connection.fetchrow(
            f"""
            UPDATE diagnostic_attempts
               SET pdf_document=COALESCE(pdf_document, $3),
                   report_assets=NULL, answers='{{}}'::jsonb,
                   report_snapshot={_SANITIZED_REVIEW_SNAPSHOT},
                   report_asset_bundle_id=NULL, updated_at=now()
             WHERE attempt_id=$1 AND pdf_status='sending' AND pdf_locked_at=$2
            RETURNING attempt_id
            """,
            attempt_id,
            lease,
            document,
        )
        return row is not None


async def supersede_stale_attempt(attempt_id: str, user_id: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as connection:
        async with connection.transaction():
            await connection.execute("SELECT pg_advisory_xact_lock($1)", user_id)
            row = await connection.fetchrow(
                """
                UPDATE diagnostic_attempts
                   SET status='superseded', updated_at=now()
                 WHERE attempt_id=$1 AND user_id=$2 AND status='in_progress'
                RETURNING attempt_id
                """,
                attempt_id,
                user_id,
            )
            if row is None:
                return False
            await connection.execute(
                """
                UPDATE diagnostic_notifications
                   SET status='cancelled', locked_at=NULL, updated_at=now()
                 WHERE attempt_id=$1 AND kind='incomplete'
                   AND status IN ('pending', 'failed', 'sending')
                """,
                attempt_id,
            )
            return True
        return row is not None


async def mark_pdf_failed(attempt_id: str, lease: datetime, error_text: str) -> bool:
    pool = await get_pool()
    async with pool.acquire() as connection:
        row = await connection.fetchrow(
            f"""
            UPDATE diagnostic_attempts
               SET pdf_status=CASE WHEN pdf_attempts >= 8 THEN 'abandoned' ELSE 'failed' END,
                   pdf_locked_at=NULL, pdf_last_error=$2,
                   pdf_document=CASE WHEN pdf_attempts >= 8 THEN NULL ELSE pdf_document END,
                   report_assets=CASE WHEN pdf_attempts >= 8 THEN NULL ELSE report_assets END,
                   answers=CASE WHEN pdf_attempts >= 8 THEN '{{}}'::jsonb ELSE answers END,
                   report_snapshot=CASE WHEN pdf_attempts >= 8
                       THEN {_SANITIZED_REVIEW_SNAPSHOT}
                       ELSE report_snapshot END,
                   report_asset_bundle_id=CASE WHEN pdf_attempts >= 8 THEN NULL ELSE report_asset_bundle_id END,
                   updated_at=now()
             WHERE attempt_id=$1 AND pdf_status='sending' AND pdf_locked_at=$3
            RETURNING attempt_id
            """,
            attempt_id,
            _safe_error(error_text),
            lease,
        )
        return row is not None


async def claim_due_notifications(limit: int = 1) -> list:
    pool = await get_pool()
    async with pool.acquire() as connection:
        async with connection.transaction():
            await connection.execute(
                """
                UPDATE diagnostic_notifications
                   SET status='abandoned', locked_at=NULL,
                       last_error='retry_limit_reached', updated_at=now()
                 WHERE status='sending' AND attempts >= 8
                   AND locked_at <= now() - interval '10 minutes'
                """
            )
            rows = await connection.fetch(
                """
                SELECT * FROM diagnostic_notifications
                 WHERE due_at <= now() AND attempts < 8
                   AND NOT EXISTS (
                       SELECT 1 FROM diagnostic_erased_users erased
                        WHERE erased.user_id=diagnostic_notifications.user_id
                          AND erased.erased_at > now() - interval '15 minutes'
                   )
                   AND (status='pending'
                     OR (status='failed' AND updated_at <= now() - interval '5 minutes')
                     OR (status='sending' AND locked_at <= now() - interval '10 minutes'))
                 ORDER BY due_at FOR UPDATE SKIP LOCKED LIMIT $1
                """,
                1,
            )
            return [
                await connection.fetchrow(
                    """
                    UPDATE diagnostic_notifications
                       SET status='sending', locked_at=now(), attempts=attempts+1, updated_at=now()
                     WHERE id=$1 RETURNING *
                    """,
                    row["id"],
                )
                for row in rows
            ]


async def mark_notification_sent(notification_id: int, lease: datetime) -> bool:
    pool = await get_pool()
    async with pool.acquire() as connection:
        row = await connection.fetchrow(
            """
            UPDATE diagnostic_notifications
               SET status='sent', sent_at=now(), locked_at=NULL, last_error=NULL, updated_at=now()
             WHERE id=$1 AND status='sending' AND locked_at=$2
            RETURNING id
            """,
            notification_id,
            lease,
        )
        return row is not None


async def notification_is_sent(notification_id: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as connection:
        return bool(await connection.fetchval(
            "SELECT status='sent' FROM diagnostic_notifications WHERE id=$1",
            notification_id,
        ))


async def mark_notification_failed(
    notification_id: int, lease: datetime, error_text: str
) -> bool:
    pool = await get_pool()
    async with pool.acquire() as connection:
        row = await connection.fetchrow(
            """
            UPDATE diagnostic_notifications
               SET status=CASE WHEN attempts >= 8 THEN 'abandoned' ELSE 'failed' END,
                   locked_at=NULL, last_error=$2, updated_at=now()
             WHERE id=$1 AND status='sending' AND locked_at=$3
            RETURNING id
            """,
            notification_id,
            _safe_error(error_text),
            lease,
        )
        return row is not None


async def get_claimed_notification(notification_id: int, lease: datetime):
    """Reload delivery eligibility only while the caller owns the exact lease."""
    pool = await get_pool()
    async with pool.acquire() as connection:
        return await connection.fetchrow(
            """
            SELECT n.*, a.status AS attempt_status, a.result_viewed_at,
                   a.subject, a.mode, a.diagnostic_id,
                   EXISTS (
                       SELECT 1 FROM diagnostic_attempts AS later
                        WHERE later.user_id=n.user_id
                          AND later.diagnostic_id=a.diagnostic_id
                          AND later.status IN ('in_progress', 'completed')
                          AND later.mode='full'
                          AND COALESCE(later.completed_at, later.started_at) > a.completed_at
                   ) AS has_later_full
              FROM diagnostic_notifications AS n
              LEFT JOIN diagnostic_attempts AS a ON a.attempt_id=n.attempt_id
             WHERE n.id=$1 AND n.status='sending' AND n.locked_at=$2
               AND NOT EXISTS (
                   SELECT 1 FROM diagnostic_erased_users erased
                    WHERE erased.user_id=n.user_id
                      AND erased.erased_at > now() - interval '15 minutes'
               )
            """,
            notification_id,
            lease,
        )


async def cancel_notification(notification_id: int, lease: datetime) -> bool:
    pool = await get_pool()
    async with pool.acquire() as connection:
        row = await connection.fetchrow(
            """
            UPDATE diagnostic_notifications
               SET status='cancelled', locked_at=NULL, updated_at=now()
             WHERE id=$1 AND status='sending' AND locked_at=$2
            RETURNING id
            """,
            notification_id,
            lease,
        )
        return row is not None


def _safe_error(error_text: str) -> str:
    return (error_text or "unknown_error").replace("\x00", "")[:1000]
