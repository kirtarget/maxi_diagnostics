"""Privacy-safe funnel events and their windowed aggregation.

A row carries a pseudonymous subject hash derived exactly like the offer events,
one funnel step, and the optional exam/subject the step belongs to. No Telegram
identifier, profile field, answer or payload is stored. Days are recorded in UTC
so that the return-rate arithmetic stays inside one calendar system.
"""

from __future__ import annotations

import logging
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
    (*FUNNEL_STEPS, "trainer_answered", "offer_clicked")
)
FUNNEL_RETENTION_DAYS: Final[int] = 90
_COUNTED_ACTIONS: Final[tuple[str, ...]] = (
    *FUNNEL_STEPS,
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
    )
"""
_SUMMARY_SQL = (
    _WINDOW
    + """
    SELECT
        (SELECT count(DISTINCT subject_hash) FROM window_events) AS subjects,
        (SELECT count(DISTINCT subject_hash) FROM window_events
          WHERE action='opened') AS opened,
        (SELECT count(DISTINCT subject_hash) FROM window_events
          WHERE action='started') AS started,
        (SELECT count(DISTINCT subject_hash) FROM window_events
          WHERE action='completed') AS completed,
        (SELECT count(DISTINCT subject_hash) FROM window_events
          WHERE action='result_viewed') AS result_viewed,
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
) -> bool:
    """Append one funnel event. Never raises into the request or bot path."""
    try:
        if action not in FUNNEL_ACTIONS:
            return False
        pool = await get_pool()
        async with pool.acquire() as connection:
            await connection.execute(
                """
                INSERT INTO diagnostic_funnel_events (subject_hash, action, exam, subject)
                VALUES ($1, $2, $3, $4)
                """,
                session_subject_key(application_secret, user_id),
                action,
                _bounded(exam, _MAX_EXAM_LENGTH),
                _bounded(subject, _MAX_SUBJECT_LENGTH),
            )
        return True
    except Exception as exc:
        logger.warning(
            "diagnostic_funnel_event_failed action=%s error=%s",
            action,
            type(exc).__name__,
        )
        return False


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
    counts = {key: int(summary[key]) for key in ("subjects", *_COUNTED_ACTIONS)}
    counts["returned_d1"] = int(summary["returned_d1"])
    counts["returned_d7"] = int(summary["returned_d7"])
    return {
        "days": window,
        "exam": exam_filter,
        "subject": subject_filter,
        "summary": counts,
        "breakdown": [
            {
                "exam": str(row["exam"]),
                "subject": str(row["subject"]),
                "started": int(row["started"]),
                "completed": int(row["completed"]),
                "result_viewed": int(row["result_viewed"]),
                "trainer_answered": int(row["trainer_answered"]),
            }
            for row in breakdown
        ],
    }
