"""Server-owned gameplay events and the compact profile projection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from typing import Any
from zoneinfo import ZoneInfo


_QUEST_KEY = "complete_3_activities"
_QUEST_TARGET = 3
_REWARD_XP = {"quick": 20, "full": 40}
_LEVEL_THRESHOLDS = (0, 100, 250, 500, 900)


@dataclass(frozen=True)
class GameplayEvent:
    """A fully server-resolved event ready for one transactional insert."""

    user_id: int
    idempotency_key: str
    fingerprint: str
    event_type: str
    source_type: str
    source_id: str
    activity_date: date
    xp_delta: int


def _event_fingerprint(
    *, event_type: str, source_type: str, source_id: str, activity_date: date,
    xp_delta: int, policy: str = "diagnostic-completion-v1"
) -> str:
    payload = {
        "activity_date": activity_date.isoformat(),
        "event_type": event_type,
        "policy": policy,
        "source_id": source_id,
        "source_type": source_type,
        "xp_delta": xp_delta,
    }
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("ascii")).hexdigest()


def build_diagnostic_completion_event(
    *,
    user_id: int,
    attempt_id: str,
    mode: str,
    timezone_name: str = "Europe/Moscow",
    now: datetime | None = None,
) -> GameplayEvent:
    """Resolve reward and local date without reading client-authored data."""
    try:
        xp_delta = _REWARD_XP[mode]
    except KeyError as exc:
        raise ValueError("diagnostic_mode_invalid") from exc
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    activity_date = instant.astimezone(ZoneInfo(timezone_name)).date()
    event_type = f"diagnostic_{mode}_completed"
    source_type = "diagnostic_completion"
    idempotency_key = f"diagnostic-completion/{attempt_id}"
    return GameplayEvent(
        user_id=user_id,
        idempotency_key=idempotency_key,
        fingerprint=_event_fingerprint(
            event_type=event_type,
            source_type=source_type,
            source_id=attempt_id,
            activity_date=activity_date,
            xp_delta=xp_delta,
        ),
        event_type=event_type,
        source_type=source_type,
        source_id=attempt_id,
        activity_date=activity_date,
        xp_delta=xp_delta,
    )


def build_trainer_answer_event(
    *, user_id: int, session_id: str, question_id: str,
    timezone_name: str = "Europe/Moscow", now: datetime | None = None,
) -> GameplayEvent:
    """Build the exactly-once XP event for one correct trainer answer."""
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    activity_date = instant.astimezone(ZoneInfo(timezone_name)).date()
    source_id = f"{session_id}/{question_id}"
    return GameplayEvent(
        user_id=user_id,
        idempotency_key=f"trainer-answer/{source_id}",
        fingerprint=_event_fingerprint(
            event_type="trainer_answer_correct",
            source_type="trainer_answer",
            source_id=source_id,
            activity_date=activity_date,
            xp_delta=10,
            policy="trainer-answer-v1",
        ),
        event_type="trainer_answer_correct",
        source_type="trainer_answer",
        source_id=source_id,
        activity_date=activity_date,
        xp_delta=10,
    )


async def apply_gameplay_event(connection, event: GameplayEvent) -> bool:
    """Insert one event and project it exactly once.

    The caller owns the user advisory lock and transaction. A same-key retry with
    the same fingerprint is a no-op. A different fingerprint is a conflict.
    """
    inserted = await connection.fetchrow(
        """
        INSERT INTO diagnostic_progress_events (
            user_id, idempotency_key, fingerprint, event_type, source_type,
            source_id, activity_date, xp_delta
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
        ON CONFLICT (user_id, idempotency_key) DO NOTHING
        RETURNING event_id
        """,
        event.user_id,
        event.idempotency_key,
        event.fingerprint,
        event.event_type,
        event.source_type,
        event.source_id,
        event.activity_date,
        event.xp_delta,
    )
    if inserted is None:
        existing = await connection.fetchrow(
            """
            SELECT fingerprint FROM diagnostic_progress_events
             WHERE user_id=$1 AND idempotency_key=$2
            """,
            event.user_id,
            event.idempotency_key,
        )
        if existing is None:
            raise RuntimeError("diagnostic_progress_event_unavailable")
        if existing["fingerprint"] != event.fingerprint:
            raise ValueError("diagnostic_progress_event_conflict")
        return False

    await connection.execute(
        """
        INSERT INTO diagnostic_progress_profiles (user_id)
        VALUES ($1)
        ON CONFLICT (user_id) DO NOTHING
        """,
        event.user_id,
    )
    await connection.execute(
        """
        UPDATE diagnostic_progress_profiles
           SET xp_total = xp_total + $2,
               streak_days = CASE
                   WHEN streak_last_date = $3::date THEN streak_days
                   WHEN streak_last_date = ($3::date - 1) THEN streak_days + 1
                   ELSE 1
               END,
               streak_last_date = $3::date,
               daily_goal_progress = CASE
                   WHEN daily_goal_date = $3::date
                   THEN LEAST(daily_goal_target, daily_goal_progress + 1)
                   ELSE 1
               END,
               daily_goal_date = $3::date,
               quest_key = COALESCE(quest_key, $4::text),
               quest_target = COALESCE(quest_target, $5::smallint),
               quest_progress = CASE
                   WHEN quest_date = $3::date
                   THEN LEAST(COALESCE(quest_target, $5::smallint), quest_progress + 1)
                   ELSE 1
               END,
               quest_date = $3::date,
               updated_at = now()
         WHERE user_id=$1
        """,
        event.user_id,
        event.xp_delta,
        event.activity_date,
        _QUEST_KEY,
        _QUEST_TARGET,
    )
    return True


async def record_diagnostic_completion(
    connection,
    *,
    user_id: int,
    attempt_id: str,
    mode: str,
    timezone_name: str = "Europe/Moscow",
) -> bool:
    event = build_diagnostic_completion_event(
        user_id=user_id,
        attempt_id=attempt_id,
        mode=mode,
        timezone_name=timezone_name,
    )
    return await apply_gameplay_event(connection, event)


def level_for_xp(xp_total: int) -> tuple[int, int]:
    """Return one-based level and integer percentage toward the next level."""
    xp = max(int(xp_total), 0)
    level = 1
    current = _LEVEL_THRESHOLDS[0]
    for index, threshold in enumerate(_LEVEL_THRESHOLDS):
        if xp >= threshold:
            level = index + 1
            current = threshold
        else:
            break
    if xp >= _LEVEL_THRESHOLDS[-1]:
        level += (xp - _LEVEL_THRESHOLDS[-1]) // 500
        current = _LEVEL_THRESHOLDS[-1] + (level - 5) * 500
    next_threshold = (
        _LEVEL_THRESHOLDS[level]
        if level < len(_LEVEL_THRESHOLDS)
        else current + 500
    )
    progress = int((xp - current) * 100 / (next_threshold - current))
    return level, min(max(progress, 0), 100)


async def get_gameplay_profile(connection, user_id: int):
    return await connection.fetchrow(
        """
        SELECT xp_total, streak_days, streak_last_date, lives_remaining,
               lives_refill_at,
               daily_goal_target, daily_goal_progress, daily_goal_date,
               quest_key, quest_progress, quest_target, quest_date
          FROM diagnostic_progress_profiles
         WHERE user_id=$1
        """,
        user_id,
    )


def reconcile_lives(
    lives_remaining: int,
    lives_refill_at: datetime | None,
    *,
    now: datetime | None = None,
    max_lives: int = 5,
    refill_interval: timedelta = timedelta(hours=4),
) -> tuple[int, datetime | None]:
    """Pure lazy four-hour refill calculation for the profile projection."""
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    lives = min(max(int(lives_remaining), 0), max_lives)
    if lives >= max_lives:
        return max_lives, None
    if lives_refill_at is None:
        return lives, instant
    refill_at = lives_refill_at
    if refill_at.tzinfo is None:
        refill_at = refill_at.replace(tzinfo=timezone.utc)
    elapsed = instant - refill_at
    if elapsed < refill_interval:
        return lives, refill_at
    refills = int(elapsed.total_seconds() // refill_interval.total_seconds())
    lives = min(max_lives, lives + refills)
    if lives >= max_lives:
        return max_lives, None
    return lives, refill_at + (refill_interval * refills)


async def get_reconciled_profile(connection, user_id: int, *, now: datetime | None = None):
    """Lock and lazily reconcile one user's lives before a trainer mutation."""
    await connection.execute(
        """
        INSERT INTO diagnostic_progress_profiles (user_id)
        VALUES ($1)
        ON CONFLICT (user_id) DO NOTHING
        """,
        user_id,
    )
    row = await connection.fetchrow(
        """
        SELECT xp_total, streak_days, streak_last_date, lives_remaining,
               lives_refill_at, daily_goal_target, daily_goal_progress,
               daily_goal_date, quest_key, quest_progress, quest_target, quest_date
          FROM diagnostic_progress_profiles
         WHERE user_id=$1
         FOR UPDATE
        """,
        user_id,
    )
    lives, refill_at = reconcile_lives(
        row["lives_remaining"], row["lives_refill_at"], now=now
    )
    if lives != row["lives_remaining"] or refill_at != row["lives_refill_at"]:
        row = await connection.fetchrow(
            """
            UPDATE diagnostic_progress_profiles
               SET lives_remaining=$2, lives_refill_at=$3, updated_at=now()
             WHERE user_id=$1
             RETURNING xp_total, streak_days, streak_last_date, lives_remaining,
                       lives_refill_at, daily_goal_target, daily_goal_progress,
                       daily_goal_date, quest_key, quest_progress, quest_target, quest_date
            """,
            user_id, lives, refill_at,
        )
    return row


def serialize_gameplay_profile(row: Any | None, *, now: datetime | None = None) -> dict[str, Any]:
    """Allowlist only derived gameplay state for authenticated API responses."""
    def date_text(value: Any) -> str | None:
        if isinstance(value, str):
            return value
        return (
            value.isoformat()
            if value is not None and hasattr(value, "isoformat")
            else None
        )

    def nonnegative_int(value: Any, default: int) -> int:
        try:
            return max(int(value), 0)
        except (TypeError, ValueError):
            return default

    if row is None:
        xp_total = 0
        streak_days = 0
        lives_remaining = 5
        next_life_at = None
        daily_target = 1
        daily_progress = 0
        daily_date = None
        quest = None
    else:
        xp_total = nonnegative_int(row.get("xp_total", 0), 0)
        streak_days = nonnegative_int(row.get("streak_days", 0), 0)
        lives_remaining = min(nonnegative_int(row.get("lives_remaining", 5), 5), 5)
        refill_anchor = row.get("lives_refill_at")
        lives_remaining, refill_anchor = reconcile_lives(
            lives_remaining,
            refill_anchor if isinstance(refill_anchor, datetime) else None,
            now=now,
        )
        next_life_at = (
            (refill_anchor + timedelta(hours=4)).isoformat()
            if lives_remaining < 5 and refill_anchor is not None
            else None
        )
        daily_target = max(nonnegative_int(row.get("daily_goal_target", 1), 1), 1)
        daily_progress = min(nonnegative_int(row.get("daily_goal_progress", 0), 0), daily_target)
        daily_date = row.get("daily_goal_date")
        quest_key = row.get("quest_key")
        quest_target = row.get("quest_target")
        quest = (
            {
                "key": quest_key,
                "date": date_text(row.get("quest_date")),
                "target": nonnegative_int(quest_target, 1),
                "progress": min(
                    nonnegative_int(row.get("quest_progress", 0), 0),
                    nonnegative_int(quest_target, 1),
                ),
            }
            if isinstance(quest_key, str) and quest_key and quest_target is not None
            else None
        )
    level, level_progress = level_for_xp(xp_total)
    return {
        "xp_total": xp_total,
        "level": level,
        "level_progress": level_progress,
        "streak_days": streak_days,
        "lives_remaining": lives_remaining,
        "next_life_at": next_life_at,
        "daily_goal": {
            "date": date_text(daily_date),
            "target": daily_target,
            "progress": daily_progress,
            "complete": daily_progress >= daily_target,
        },
        "quest": quest,
    }
