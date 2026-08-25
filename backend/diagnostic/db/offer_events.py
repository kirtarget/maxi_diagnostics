"""Privacy-safe, server-timestamped school offer events."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Final


OFFER_PLACEMENTS: Final[frozenset[str]] = frozenset(
    {"home", "diagnostic_result", "trainer"}
)
EVENT_TYPES: Final[frozenset[str]] = frozenset({"impression", "click", "dismiss"})
MAX_EVENTS_PER_SUBJECT_PER_HOUR: Final[int] = 120
OFFER_EVENT_RETENTION_DAYS: Final[int] = 90


def event_fingerprint(
    *, event_id: str, subject_hash: str, placement: str, offer_id: str, event_type: str
) -> str:
    payload = {
        "event_id": event_id,
        "event_type": event_type,
        "offer_id": offer_id,
        "placement": placement,
        "subject_hash": subject_hash,
        "version": "offer-event-v1",
    }
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("ascii")).hexdigest()


async def record_offer_event(
    connection,
    *,
    event_id: str,
    subject_hash: str,
    placement: str,
    offer_id: str,
    event_type: str,
    now: datetime | None = None,
    max_events_per_hour: int = MAX_EVENTS_PER_SUBJECT_PER_HOUR,
) -> bool:
    """Insert one event, returning false for an exact idempotent retry.

    The caller owns the transaction. A subject advisory lock makes the bounded
    hourly count and insert atomic without storing a Telegram identifier.
    """
    fingerprint = event_fingerprint(
        event_id=event_id,
        subject_hash=subject_hash,
        placement=placement,
        offer_id=offer_id,
        event_type=event_type,
    )
    existing = await connection.fetchrow(
        "SELECT fingerprint FROM diagnostic_offer_events WHERE event_id=$1",
        event_id,
    )
    if existing is not None:
        if existing["fingerprint"] != fingerprint:
            raise ValueError("offer_event_conflict")
        return False

    await connection.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended($1, 641993))",
        subject_hash,
    )
    # A concurrent retry may have inserted the same event while this request
    # waited for the subject lock. Re-check before enforcing the rate limit.
    existing = await connection.fetchrow(
        "SELECT fingerprint FROM diagnostic_offer_events WHERE event_id=$1",
        event_id,
    )
    if existing is not None:
        if existing["fingerprint"] != fingerprint:
            raise ValueError("offer_event_conflict")
        return False
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    since = instant - timedelta(hours=1)
    recent = await connection.fetchval(
        """
        SELECT count(*)
          FROM diagnostic_offer_events
         WHERE subject_hash=$1 AND occurred_at >= $2
        """,
        subject_hash,
        since,
    )
    if int(recent or 0) >= max_events_per_hour:
        raise ValueError("offer_event_rate_limited")

    inserted = await connection.fetchrow(
        """
        INSERT INTO diagnostic_offer_events
            (event_id, subject_hash, placement, offer_id, event_type, fingerprint, occurred_at)
        VALUES ($1,$2,$3,$4,$5,$6,$7)
        ON CONFLICT (event_id) DO NOTHING
        RETURNING event_id
        """,
        event_id,
        subject_hash,
        placement,
        offer_id,
        event_type,
        fingerprint,
        instant,
    )
    if inserted is None:
        existing = await connection.fetchrow(
            "SELECT fingerprint FROM diagnostic_offer_events WHERE event_id=$1",
            event_id,
        )
        if existing is None:
            raise RuntimeError("offer_event_unavailable")
        if existing["fingerprint"] != fingerprint:
            raise ValueError("offer_event_conflict")
        return False
    return True


async def purge_offer_events(connection, *, retention_days: int = OFFER_EVENT_RETENTION_DAYS,
                             limit: int = 1000) -> int:
    """Bounded retention purge. No event payload is exported before deletion."""
    if retention_days < 1 or limit < 1 or limit > 10_000:
        raise ValueError("invalid_offer_event_retention")
    rows = await connection.fetch(
        """
        DELETE FROM diagnostic_offer_events
         WHERE event_id IN (
             SELECT event_id FROM diagnostic_offer_events
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
