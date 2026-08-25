"""Privacy-safe weekly league aggregation over server-owned XP events."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import hmac
from typing import Any
from zoneinfo import ZoneInfo


COHORT_BUCKETS = 32
MAX_COHORT_SIZE = 30
MAX_ROWS = 10
MIN_PARTICIPANTS = 5


@dataclass(frozen=True)
class LeagueWeek:
    """A closed local-date interval used by the weekly leaderboard."""

    key: str
    start: date
    end: date

    @property
    def end_exclusive(self) -> date:
        return self.end + timedelta(days=1)


def current_week(*, timezone_name: str, now: datetime | None = None) -> LeagueWeek:
    """Return the Monday-Sunday week containing ``now`` in school timezone."""
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    local_date = instant.astimezone(ZoneInfo(timezone_name)).date()
    start = local_date - timedelta(days=local_date.weekday())
    return LeagueWeek(key=start.isoformat(), start=start, end=start + timedelta(days=6))


def _cohort_digest(application_secret: str, week_key: str, user_id: int) -> bytes:
    material = f"{week_key}{user_id}".encode("utf-8")
    return hmac.new(application_secret.encode("utf-8"), material, hashlib.sha256).digest()


def cohort_bucket(application_secret: str, week_key: str, user_id: int) -> int:
    """Assign a user to one stable, secret-derived weekly cohort."""
    return int.from_bytes(_cohort_digest(application_secret, week_key, user_id)[:2], "big") % COHORT_BUCKETS


def pseudonym(application_secret: str, week_key: str, user_id: int) -> str:
    """Return a deterministic public label with no Telegram-derived content."""
    token = _cohort_digest(application_secret, week_key, user_id).hex()[:8].upper()
    return f"Игрок {token}"


def _tie_key(application_secret: str, week_key: str, user_id: int) -> str:
    return _cohort_digest(application_secret, week_key, user_id).hex()


def _rank(points: int, rows: list[dict[str, Any]]) -> int:
    return 1 + sum(1 for row in rows if row["xp_week"] > points)


async def get_weekly_league(
    connection,
    *,
    user_id: int,
    application_secret: str,
    timezone_name: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build a bounded, privacy-safe response from positive XP events only.

    The query returns only grouped positive XP totals. User identifiers are used
    transiently for the secret cohort calculation and never enter the response.
    """
    week = current_week(timezone_name=timezone_name, now=now)
    aggregate_rows = await connection.fetch(
        """
        SELECT user_id, SUM(xp_delta)::integer AS xp_week
          FROM diagnostic_progress_events
         WHERE activity_date >= $1::date
           AND activity_date < $2::date
           AND xp_delta > 0
         GROUP BY user_id
        """,
        week.start,
        week.end_exclusive,
    )

    user_bucket = cohort_bucket(application_secret, week.key, user_id)
    all_cohort = [
        {
            "user_id": int(row["user_id"]),
            "xp_week": max(int(row["xp_week"]), 0),
            "tie_key": _tie_key(application_secret, week.key, int(row["user_id"])),
        }
        for row in aggregate_rows
        if cohort_bucket(application_secret, week.key, int(row["user_id"])) == user_bucket
    ]
    all_cohort.sort(key=lambda row: (-row["xp_week"], row["tie_key"]))
    cohort = all_cohort[:MAX_COHORT_SIZE]

    me = next((row for row in all_cohort if row["user_id"] == user_id), None)
    if me is None:
        me_total = await connection.fetchval(
            """
            SELECT COALESCE(SUM(xp_delta), 0)::integer
              FROM diagnostic_progress_events
             WHERE user_id=$1
               AND activity_date >= $2::date
               AND activity_date < $3::date
               AND xp_delta > 0
            """,
            user_id,
            week.start,
            week.end_exclusive,
        )
        me_total = max(int(me_total or 0), 0)
        if me_total > 0:
            me = {
                "user_id": user_id,
                "xp_week": me_total,
                "tie_key": _tie_key(application_secret, week.key, user_id),
            }

    participant_count = min(len(all_cohort), MAX_COHORT_SIZE)
    me_payload = {
        "rank": (
            _rank(me["xp_week"], all_cohort)
            if me is not None and any(row["user_id"] == user_id for row in cohort)
            else None
        ),
        "xp_week": me["xp_week"] if me is not None else 0,
    }
    forming = participant_count < MIN_PARTICIPANTS
    rows = []
    if not forming:
        for row in cohort[:MAX_ROWS]:
            rows.append(
                {
                    "rank": _rank(row["xp_week"], all_cohort),
                    "display_label": pseudonym(
                        application_secret, week.key, row["user_id"]
                    ),
                    "xp_week": row["xp_week"],
                    "is_me": row["user_id"] == user_id,
                }
            )

    return {
        "ok": True,
        "week_key": week.key,
        "week_start": week.start.isoformat(),
        "week_end": week.end.isoformat(),
        "status": "forming" if forming else "active",
        "participant_count": participant_count,
        "rows": rows,
        "me": me_payload,
    }
