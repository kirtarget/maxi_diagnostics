"""Server-owned gameplay events and the compact profile projection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
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
    *, event_type: str, source_type: str, source_id: str, activity_date: date, xp_delta: int
) -> str:
    payload = {
        "activity_date": activity_date.isoformat(),
        "event_type": event_type,
        "policy": "diagnostic-completion-v1",
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
               daily_goal_target, daily_goal_progress, daily_goal_date,
               quest_key, quest_progress, quest_target, quest_date
          FROM diagnostic_progress_profiles
         WHERE user_id=$1
        """,
        user_id,
    )


def serialize_gameplay_profile(row: Any | None) -> dict[str, Any]:
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
        daily_target = 1
        daily_progress = 0
        daily_date = None
        quest = None
    else:
        xp_total = nonnegative_int(row.get("xp_total", 0), 0)
        streak_days = nonnegative_int(row.get("streak_days", 0), 0)
        lives_remaining = min(nonnegative_int(row.get("lives_remaining", 5), 5), 5)
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
        "daily_goal": {
            "date": date_text(daily_date),
            "target": daily_target,
            "progress": daily_progress,
            "complete": daily_progress >= daily_target,
        },
        "quest": quest,
    }
