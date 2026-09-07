"""Privacy-safe funnel events and their windowed aggregation.

A row carries a pseudonymous subject hash derived exactly like the offer events,
one funnel step, and the optional exam/subject the step belongs to. No Telegram
identifier, profile field, answer or payload is stored. Days are recorded in UTC
so that the return-rate arithmetic stays inside one calendar system.
"""

from __future__ import annotations

import logging
import hashlib
from typing import Any, Final

from diagnostic.db.core import get_pool
from diagnostic.session_identity import session_subject_key


logger = logging.getLogger(__name__)

FUNNEL_STEPS: Final[tuple[str, ...]] = (
    "opened",
    "started",
    "completed",
    "result_viewed",
)
FUNNEL_ACTIONS: Final[frozenset[str]] = frozenset(
    (*FUNNEL_STEPS, "question_skipped", "trainer_answered", "offer_clicked",
     "registration_started", "registration_completed", "onboarding_started",
     "onboarding_completed", "diagnostic_started", "question_answered",
     "diagnostic_abandoned", "diagnostic_completed", "daily_started",
     "daily_completed", "life_lost", "streak_updated", "notification_sent",
     "notification_opened", "user_returned")
)
FUNNEL_RETENTION_DAYS: Final[int] = 90
_COUNTED_ACTIONS: Final[tuple[str, ...]] = (
    *FUNNEL_STEPS,
    "question_skipped",
    "trainer_answered",
    "offer_clicked",
)
_MAX_EXAM_LENGTH: Final[int] = 32
_MAX_SUBJECT_LENGTH: Final[int] = 128

_WINDOW = """
    WITH window_events AS (
        SELECT subject_hash, action, occurred_on
          FROM diagnostic_funnel_events
         WHERE occurred_on > (now() AT TIME ZONE 'UTC')::date - $1::int
           AND ($2::text IS NULL OR exam = $2::text)
           AND ($3::text IS NULL OR subject = $3::text)
    ),
    subject_days AS (
        SELECT DISTINCT subject_hash, occurred_on FROM window_events
         WHERE action IN (
             'opened', 'started', 'completed', 'result_viewed', 'trainer_answered',
             'offer_clicked', 'onboarding_started', 'onboarding_completed',
             'diagnostic_started', 'question_answered', 'diagnostic_completed',
             'daily_started', 'daily_completed', 'notification_opened', 'user_returned'
         )
    )
"""
_SUMMARY_SQL = (
    _WINDOW
    + """
    SELECT
        (SELECT count(DISTINCT subject_hash) FROM subject_days) AS subjects,
        (SELECT count(DISTINCT subject_hash) FROM window_events
          WHERE action='opened') AS opened,
        (SELECT count(DISTINCT subject_hash) FROM window_events
          WHERE action='started') AS started,
        (SELECT count(DISTINCT subject_hash) FROM window_events
          WHERE action='completed') AS completed,
        (SELECT count(DISTINCT subject_hash) FROM window_events
          WHERE action='result_viewed') AS result_viewed,
        (SELECT count(*) FROM window_events
          WHERE action='question_skipped') AS question_skipped,
        (SELECT count(DISTINCT subject_hash) FROM window_events
          WHERE action='trainer_answered') AS trainer_answered,
        (SELECT count(DISTINCT subject_hash) FROM window_events
          WHERE action='offer_clicked') AS offer_clicked,
        (SELECT count(DISTINCT day.subject_hash) FROM subject_days AS day
          WHERE EXISTS (
              SELECT 1 FROM subject_days AS later
               WHERE later.subject_hash=day.subject_hash
                 AND later.occurred_on = day.occurred_on + 1
          )) AS returned_d1,
        (SELECT count(DISTINCT day.subject_hash) FROM subject_days AS day
          WHERE EXISTS (
              SELECT 1 FROM subject_days AS later
               WHERE later.subject_hash=day.subject_hash
                 AND later.occurred_on BETWEEN day.occurred_on + 2 AND day.occurred_on + 7
          )) AS returned_d7
    """
)
_BREAKDOWN_SQL = """
    SELECT exam, subject,
           count(DISTINCT subject_hash) FILTER (WHERE action='started') AS started,
           count(DISTINCT subject_hash) FILTER (WHERE action='completed') AS completed,
           count(DISTINCT subject_hash) FILTER (WHERE action='result_viewed') AS result_viewed,
           count(*) FILTER (WHERE action='question_skipped') AS question_skipped,
           count(DISTINCT subject_hash) FILTER (WHERE action='trainer_answered') AS trainer_answered
      FROM diagnostic_funnel_events
     WHERE occurred_on > (now() AT TIME ZONE 'UTC')::date - $1::int
       AND exam IS NOT NULL AND subject IS NOT NULL
       AND ($2::text IS NULL OR exam = $2::text)
       AND ($3::text IS NULL OR subject = $3::text)
     GROUP BY exam, subject
     ORDER BY exam, subject
     LIMIT 200
"""


def _bounded(value: Any, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed[:limit] or None


def _window_days(days: int) -> int:
    if days not in (7, 30):
        raise ValueError("funnel_window_invalid")
    return days


async def record_event(
    *,
    application_secret: str,
    user_id: int,
    action: str,
    exam: Any = None,
    subject: Any = None,
    dedupe_key: str | None = None,
) -> bool:
    """Append one funnel event. Never raises into the request or bot path."""
    try:
        if action not in FUNNEL_ACTIONS:
            return False
        pool = await get_pool()
        async with pool.acquire() as connection:
            await connection.execute(
                """
                INSERT INTO diagnostic_funnel_events (subject_hash, action, exam, subject, dedupe_hash)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (subject_hash, action, dedupe_hash) DO NOTHING
                """,
                session_subject_key(application_secret, user_id),
                action,
                _bounded(exam, _MAX_EXAM_LENGTH),
                _bounded(subject, _MAX_SUBJECT_LENGTH),
                hashlib.sha256(dedupe_key.encode()).hexdigest() if dedupe_key else None,
            )
        return True
    except Exception as exc:
        logger.warning(
            "diagnostic_funnel_event_failed action=%s error=%s",
            action,
            type(exc).__name__,
        )
        return False


async def record_abandoned_attempts(application_secret: str, *, limit: int = 500) -> int:
    """Infer abandonment once after 24 hours without saved diagnostic progress."""
    try:
        pool = await get_pool()
        async with pool.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT a.attempt_id, a.user_id, a.exam, a.subject
                  FROM diagnostic_attempts a
                 WHERE a.status='in_progress' AND a.updated_at <= now() - interval '24 hours'
                   AND NOT EXISTS (
                       SELECT 1 FROM diagnostic_funnel_events event
                        WHERE event.action='diagnostic_abandoned'
                          AND event.dedupe_hash=encode(sha256(convert_to('abandoned/' || a.attempt_id, 'UTF8')), 'hex')
                   )
                 ORDER BY a.updated_at, a.attempt_id LIMIT $1
                """, max(1, min(limit, 500)),
            )
        recorded = 0
        for row in rows:
            recorded += await record_event(
                application_secret=application_secret, user_id=row["user_id"],
                action="diagnostic_abandoned", exam=row["exam"], subject=row["subject"],
                dedupe_key=f"abandoned/{row['attempt_id']}",
            )
        return recorded
    except Exception as exc:
        logger.warning("diagnostic_abandonment_scan_failed error=%s", type(exc).__name__)
        return 0


async def purge_funnel_events(
    connection, *, retention_days: int = FUNNEL_RETENTION_DAYS, limit: int = 5_000
) -> int:
    """Bounded retention purge. No event content leaves the database."""
    if retention_days < 1 or limit < 1 or limit > 50_000:
        raise ValueError("invalid_funnel_event_retention")
    rows = await connection.fetch(
        """
        DELETE FROM diagnostic_funnel_events
         WHERE event_id IN (
             SELECT event_id FROM diagnostic_funnel_events
              WHERE occurred_at < now() - ($1::int * interval '1 day')
              ORDER BY occurred_at
              LIMIT $2
         )
        RETURNING event_id
        """,
        retention_days,
        limit,
    )
    return len(rows)


async def funnel_report(
    *, days: int, exam: str | None = None, subject: str | None = None
) -> dict[str, Any]:
    """Return the windowed funnel with its per exam/subject breakdown."""
    window = _window_days(days)
    exam_filter = _bounded(exam, _MAX_EXAM_LENGTH)
    subject_filter = _bounded(subject, _MAX_SUBJECT_LENGTH)
    pool = await get_pool()
    async with pool.acquire() as connection:
        summary = await connection.fetchrow(
            _SUMMARY_SQL, window, exam_filter, subject_filter
        )
        breakdown = await connection.fetch(
            _BREAKDOWN_SQL, window, exam_filter, subject_filter
        )
        event_counts = await connection.fetch(
            """
            SELECT action, count(*) AS events, count(DISTINCT subject_hash) AS users
              FROM diagnostic_funnel_events
             WHERE occurred_on > (now() AT TIME ZONE 'UTC')::date - $1::int
               AND ($2::text IS NULL OR exam=$2) AND ($3::text IS NULL OR subject=$3)
             GROUP BY action ORDER BY action
            """, window, exam_filter, subject_filter,
        )
    counts = {key: int(summary[key]) for key in ("subjects", *_COUNTED_ACTIONS)}
    counts["returned_d1"] = int(summary["returned_d1"])
    counts["returned_d7"] = int(summary["returned_d7"])
    return {
        "days": window,
        "exam": exam_filter,
        "subject": subject_filter,
        "summary": counts,
        "events": [{"action": row["action"], "events": int(row["events"]),
                    "users": int(row["users"])} for row in event_counts],
        "breakdown": [
            {
                "exam": str(row["exam"]),
                "subject": str(row["subject"]),
                "started": int(row["started"]),
                "completed": int(row["completed"]),
                "result_viewed": int(row["result_viewed"]),
                "question_skipped": int(row["question_skipped"]),
                "trainer_answered": int(row["trainer_answered"]),
            }
            for row in breakdown
        ],
    }
