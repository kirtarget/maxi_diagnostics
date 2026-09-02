"""Transactional persistence for the server-owned trainer loop."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Any, Mapping

from diagnostic.db import gameplay
from diagnostic.db.attempts import _raise_if_erased
from diagnostic.db.core import get_pool


def answer_fingerprint(
    *, session_id: str, question_id: str, answer: Any, revision: int,
    idempotency_key: str,
) -> str:
    payload = {
        "answer": answer,
        "idempotency_key": idempotency_key,
        "question_id": question_id,
        "revision": revision,
        "session_id": session_id,
        "policy": "trainer-answer-v1",
    }
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _session_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    selected = row["selected_question_ids"]
    return {
        "trainer_session_id": row["session_id"],
        "diagnostic_id": row["diagnostic_id"],
        "content_version": row["content_version"],
        "mode": row["mode"],
        "source_attempt_id": row["source_attempt_id"],
        "question_ids": list(selected),
        "current_index": int(row["current_index"]),
        "revision": int(row["revision"]),
        "status": row["status"],
    }


def _answer_payload(
    answer_row: Mapping[str, Any], session_row: Mapping[str, Any], profile: Mapping[str, Any],
    *, now: datetime | None = None,
) -> dict[str, Any]:
    feedback = answer_row["public_feedback"] or {}
    profile_payload = gameplay.serialize_gameplay_profile(profile, now=now)
    return {
        "ok": True,
        "trainer_session_id": session_row["session_id"],
        "question_id": answer_row["question_id"],
        "is_correct": bool(answer_row["is_correct"]),
        "correct_answer": feedback.get("correct_answer"),
        "explanation": feedback.get("explanation"),
        "xp_delta": int(answer_row["xp_delta"]),
        "life_delta": int(answer_row["life_delta"]),
        "current_index": int(session_row["current_index"]),
        "revision": int(session_row["revision"]),
        "status": session_row["status"],
        "lives_remaining": profile_payload["lives_remaining"],
        "next_life_at": profile_payload["next_life_at"],
    }


async def _locked_session(connection, session_id: str, user_id: int):
    return await connection.fetchrow(
        """
        SELECT session_id, user_id, diagnostic_id, content_version, mode,
               source_attempt_id,
               selected_question_ids, current_index, revision, status,
               started_at, updated_at, completed_at
          FROM diagnostic_trainer_sessions
         WHERE session_id=$1 AND user_id=$2
         FOR UPDATE
        """,
        session_id,
        user_id,
    )


async def get_session(session_id: str, user_id: int):
    pool = await get_pool()
    async with pool.acquire() as connection:
        return await connection.fetchrow(
            """
            SELECT session_id, user_id, diagnostic_id, content_version, mode,
                   source_attempt_id,
                   selected_question_ids, current_index, revision, status,
                   started_at, updated_at, completed_at
              FROM diagnostic_trainer_sessions
             WHERE session_id=$1 AND user_id=$2
            """,
            session_id,
            user_id,
        )


async def seed_and_list_mistakes(
    *, user_id: int, diagnostic_id: str, source_attempt_id: str,
    content_version: str,
) -> list[str]:
    """Materialize unresolved questions from the owner's immutable private snapshot."""
    pool = await get_pool()
    async with pool.acquire() as connection:
        async with connection.transaction():
            await connection.execute("SELECT pg_advisory_xact_lock($1)", user_id)
            await _raise_if_erased(connection, user_id)
            await gameplay.get_reconciled_profile(connection, user_id)
            source = await connection.fetchrow(
                """
                SELECT attempt_id, diagnostic_id, content_version, status, report_snapshot
                  FROM diagnostic_attempts
                 WHERE attempt_id=$1 AND user_id=$2
                """,
                source_attempt_id,
                user_id,
            )
            if source is None or source["status"] != "completed":
                raise ValueError("trainer_mistakes_source_not_found")
            if source["diagnostic_id"] != diagnostic_id:
                raise ValueError("trainer_mistakes_source_conflict")
            if source["content_version"] != content_version:
                raise ValueError("trainer_content_changed")
            snapshot = source["report_snapshot"] or {}
            if isinstance(snapshot, str):
                try:
                    snapshot = json.loads(snapshot)
                except (TypeError, ValueError) as exc:
                    raise ValueError("trainer_mistakes_source_not_found") from exc
            private_items = snapshot.get("review_snapshot") if isinstance(snapshot, dict) else None
            if not isinstance(private_items, list):
                return []
            for item in private_items:
                if not isinstance(item, dict):
                    continue
                question_id = item.get("question_id")
                if (
                    item.get("is_correct") is False
                    and isinstance(question_id, str)
                    and item.get("user_value") is not None
                    and item.get("expected_value") is not None
                ):
                    await connection.execute(
                        """
                        INSERT INTO diagnostic_mistakes (
                            user_id, diagnostic_id, question_id,
                            source_attempt_id, source_content_version
                        ) VALUES ($1,$2,$3,$4,$5)
                        ON CONFLICT (user_id, diagnostic_id, question_id) DO UPDATE
                           SET source_attempt_id=EXCLUDED.source_attempt_id,
                               source_content_version=EXCLUDED.source_content_version,
                               created_at=EXCLUDED.created_at,
                               resolved_at=NULL
                         WHERE diagnostic_mistakes.source_attempt_id IS DISTINCT FROM EXCLUDED.source_attempt_id
                        """,
                        user_id, diagnostic_id, question_id,
                        source_attempt_id, content_version,
                    )
            rows = await connection.fetch(
                """
                SELECT question_id
                  FROM diagnostic_mistakes
                 WHERE user_id=$1 AND diagnostic_id=$2 AND resolved_at IS NULL
                 ORDER BY created_at, question_id
                """,
                user_id,
                diagnostic_id,
            )
    return [row["question_id"] for row in rows]


async def validate_mistakes_source(
    *, user_id: int, diagnostic_id: str, source_attempt_id: str,
    content_version: str,
) -> None:
    """Check mistake source ownership without changing the mistake ledger."""
    pool = await get_pool()
    async with pool.acquire() as connection:
        async with connection.transaction():
            await connection.execute("SELECT pg_advisory_xact_lock($1)", user_id)
            await _raise_if_erased(connection, user_id)
            source = await connection.fetchrow(
                """
                SELECT diagnostic_id, content_version, status
                  FROM diagnostic_attempts
                 WHERE attempt_id=$1 AND user_id=$2
                """,
                source_attempt_id,
                user_id,
            )
            if source is None or source["status"] != "completed":
                raise ValueError("trainer_mistakes_source_not_found")
            if source["diagnostic_id"] != diagnostic_id:
                raise ValueError("trainer_mistakes_source_conflict")
            if source["content_version"] != content_version:
                raise ValueError("trainer_content_changed")


async def _find_resumable_session(
    connection, *, user_id: int, diagnostic_id: str, content_version: str,
    mode: str, source_attempt_id: str | None,
):
    return await connection.fetchrow(
        """
        SELECT session_id, diagnostic_id, content_version, mode,
               source_attempt_id,
               selected_question_ids, current_index, revision, status,
               started_at, updated_at, completed_at
          FROM diagnostic_trainer_sessions
         WHERE user_id=$1 AND diagnostic_id=$2 AND content_version=$3
           AND mode=$4
           AND source_attempt_id IS NOT DISTINCT FROM $5
           AND status IN ('active', 'exhausted')
         ORDER BY updated_at DESC, started_at DESC
         LIMIT 1
         FOR UPDATE
        """,
        user_id,
        diagnostic_id,
        content_version,
        mode,
        source_attempt_id,
    )


async def get_resumable_session(
    *, user_id: int, diagnostic_id: str, content_version: str,
    mode: str, source_attempt_id: str | None = None,
) -> tuple[dict[str, Any], Mapping[str, Any]] | None:
    """Return the owner's active or exhausted session for this stable scope."""
    pool = await get_pool()
    async with pool.acquire() as connection:
        async with connection.transaction():
            await connection.execute("SELECT pg_advisory_xact_lock($1)", user_id)
            await _raise_if_erased(connection, user_id)
            profile = await gameplay.get_reconciled_profile(connection, user_id)
            row = await _find_resumable_session(
                connection,
                user_id=user_id,
                diagnostic_id=diagnostic_id,
                content_version=content_version,
                mode=mode,
                source_attempt_id=source_attempt_id,
            )
    if row is None:
        return None
    return _session_payload(row), profile


async def start_session(
    *, session_id: str, user_id: int, diagnostic_id: str, content_version: str,
    mode: str, selected_question_ids: list[str], source_attempt_id: str | None = None,
) -> tuple[dict[str, Any], Mapping[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as connection:
        async with connection.transaction():
            await connection.execute("SELECT pg_advisory_xact_lock($1)", user_id)
            await _raise_if_erased(connection, user_id)
            profile = await gameplay.get_reconciled_profile(connection, user_id)
            existing = await _find_resumable_session(
                connection,
                user_id=user_id,
                diagnostic_id=diagnostic_id,
                content_version=content_version,
                mode=mode,
                source_attempt_id=source_attempt_id,
            )
            if existing is not None:
                return _session_payload(existing), profile
            row = await connection.fetchrow(
                """
                INSERT INTO diagnostic_trainer_sessions (
                    session_id, user_id, diagnostic_id, content_version, mode,
                    source_attempt_id,
                    selected_question_ids
                ) VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb)
                RETURNING session_id, diagnostic_id, content_version, mode,
                          source_attempt_id,
                          selected_question_ids, current_index, revision, status,
                          started_at, updated_at, completed_at
                """,
                session_id,
                user_id,
                diagnostic_id,
                content_version,
                mode,
                source_attempt_id,
                selected_question_ids,
            )
    return _session_payload(row), profile


async def answer_question(
    *, session_id: str, user_id: int, question_id: str, answer: Any,
    revision: int, idempotency_key: str, fingerprint: str, is_correct: bool,
    public_feedback: dict[str, str], timezone_name: str = "Europe/Moscow",
) -> dict[str, Any]:
    pool = await get_pool()
    async with pool.acquire() as connection:
        async with connection.transaction():
            await connection.execute("SELECT pg_advisory_xact_lock($1)", user_id)
            await _raise_if_erased(connection, user_id)
            session = await _locked_session(connection, session_id, user_id)
            if session is None:
                raise ValueError("trainer_session_not_found")
            profile = await gameplay.get_reconciled_profile(connection, user_id)

            existing = await connection.fetchrow(
                """
                SELECT question_id, revision, idempotency_key, fingerprint,
                       is_correct, public_feedback, xp_delta, life_delta
                  FROM diagnostic_trainer_answers
                 WHERE session_id=$1 AND question_id=$2
                """,
                session_id,
                question_id,
            )
            if existing is None:
                existing = await connection.fetchrow(
                    """
                    SELECT question_id, revision, idempotency_key, fingerprint,
                           is_correct, public_feedback, xp_delta, life_delta
                      FROM diagnostic_trainer_answers
                     WHERE session_id=$1 AND idempotency_key=$2
                    """,
                    session_id,
                    idempotency_key,
                )
            if existing is not None:
                if (
                    existing["revision"] == revision
                    and existing["idempotency_key"] == idempotency_key
                    and existing["fingerprint"] == fingerprint
                ):
                    return _answer_payload(existing, session, profile)
                raise ValueError("trainer_answer_conflict")

            if session["status"] != "active":
                raise ValueError("trainer_session_not_active")
            if int(session["revision"]) != revision:
                raise ValueError("trainer_revision_stale")
            selected = list(session["selected_question_ids"])
            current_index = int(session["current_index"])
            if current_index >= len(selected) or selected[current_index] != question_id:
                raise ValueError("trainer_question_out_of_order")
            if (
                session["mode"] == "normal"
                and not is_correct
                and int(profile["lives_remaining"]) <= 0
            ):
                raise ValueError("trainer_no_lives")

            xp_delta = 10 if is_correct and session["mode"] == "normal" else 0
            life_delta = 0 if is_correct or session["mode"] == "mistakes" else -1
            answer_row = await connection.fetchrow(
                """
                INSERT INTO diagnostic_trainer_answers (
                    session_id, question_id, answer, revision, next_revision,
                    idempotency_key, fingerprint, is_correct, public_feedback,
                    xp_delta, life_delta
                ) VALUES ($1,$2,$3::jsonb,$4,$5,$6,$7,$8,$9::jsonb,$10,$11)
                RETURNING question_id, revision, idempotency_key, fingerprint,
                          is_correct, public_feedback, xp_delta, life_delta
                """,
                session_id,
                question_id,
                answer,
                revision,
                revision + 1,
                idempotency_key,
                fingerprint,
                is_correct,
                public_feedback,
                xp_delta,
                life_delta,
            )
            if is_correct and session["mode"] == "normal":
                await gameplay.apply_gameplay_event(
                    connection,
                    gameplay.build_trainer_answer_event(
                        user_id=user_id,
                        session_id=session_id,
                        question_id=question_id,
                        timezone_name=timezone_name,
                    ),
                )
            elif session["mode"] != "mistakes":
                now = datetime.now(timezone.utc)
                await connection.execute(
                    """
                    UPDATE diagnostic_progress_profiles
                       SET lives_remaining=lives_remaining - 1,
                           lives_refill_at=COALESCE(lives_refill_at, $2),
                           updated_at=now()
                     WHERE user_id=$1
                    """,
                    user_id,
                    now,
                )
                profile = await gameplay.get_reconciled_profile(connection, user_id)

            if session["mode"] == "mistakes" and is_correct:
                await connection.execute(
                    """
                    UPDATE diagnostic_mistakes
                       SET resolved_at=COALESCE(resolved_at, now())
                     WHERE user_id=$1 AND diagnostic_id=$2 AND question_id=$3
                       AND resolved_at IS NULL
                    """,
                    user_id, session["diagnostic_id"], question_id,
                )

            next_index = current_index + 1
            next_status = "exhausted" if next_index >= len(selected) else "active"
            session = await connection.fetchrow(
                """
                UPDATE diagnostic_trainer_sessions
                   SET current_index=$2, revision=$3, status=$4, updated_at=now()
                 WHERE session_id=$1
                 RETURNING session_id, diagnostic_id, content_version, mode,
                           source_attempt_id,
                           selected_question_ids, current_index, revision, status,
                           started_at, updated_at, completed_at
                """,
                session_id,
                next_index,
                revision + 1,
                next_status,
            )
            if is_correct:
                profile = await gameplay.get_reconciled_profile(connection, user_id)
            return _answer_payload(answer_row, session, profile)


async def finish_session(*, session_id: str, user_id: int, revision: int) -> dict[str, Any]:
    pool = await get_pool()
    async with pool.acquire() as connection:
        async with connection.transaction():
            await connection.execute("SELECT pg_advisory_xact_lock($1)", user_id)
            await _raise_if_erased(connection, user_id)
            session = await _locked_session(connection, session_id, user_id)
            if session is None:
                raise ValueError("trainer_session_not_found")
            if session["status"] != "completed":
                if session["status"] != "exhausted":
                    raise ValueError("trainer_session_incomplete")
                if int(session["revision"]) != revision:
                    raise ValueError("trainer_revision_stale")
                session = await connection.fetchrow(
                    """
                    UPDATE diagnostic_trainer_sessions
                       SET status='completed', completed_at=now(), updated_at=now()
                     WHERE session_id=$1
                     RETURNING session_id, diagnostic_id, content_version, mode,
                               source_attempt_id,
                               selected_question_ids, current_index, revision, status,
                               started_at, updated_at, completed_at
                    """,
                    session_id,
                )
            stats = await connection.fetchrow(
                """
                SELECT count(*)::int AS answered,
                       count(*) FILTER (WHERE is_correct)::int AS correct_count,
                       coalesce(sum(xp_delta), 0)::int AS xp_earned,
                       coalesce(sum(-life_delta), 0)::int AS lives_spent
                  FROM diagnostic_trainer_answers
                 WHERE session_id=$1
                """,
                session_id,
            )
            profile = await gameplay.get_reconciled_profile(connection, user_id)
    return {
        "ok": True,
        "trainer_session_id": session_id,
        "status": session["status"],
        "revision": int(session["revision"]),
        "current_index": int(session["current_index"]),
        "question_count": len(session["selected_question_ids"]),
        "answered_count": int(stats["answered"]),
        "correct_count": int(stats["correct_count"]),
        "xp_earned": int(stats["xp_earned"]),
        "lives_spent": int(stats["lives_spent"]),
        "lives_remaining": int(profile["lives_remaining"]),
    }


async def schedule_lives_refill_reminder(
    user_id: int, *, now: datetime | None = None
) -> str | None:
    """Queue one Telegram reminder for when the next trainer life arrives."""
    pool = await get_pool()
    async with pool.acquire() as connection:
        async with connection.transaction():
            await connection.execute("SELECT pg_advisory_xact_lock($1)", user_id)
            await _raise_if_erased(connection, user_id)
            profile = await gameplay.get_reconciled_profile(connection, user_id, now=now)
            anchor = profile["lives_refill_at"]
            if int(profile["lives_remaining"]) >= 5 or anchor is None:
                return None
            if anchor.tzinfo is None:
                anchor = anchor.replace(tzinfo=timezone.utc)
            due_at = anchor + timedelta(hours=4)
            await connection.execute(
                """
                INSERT INTO diagnostic_notifications (dedupe_key, user_id, kind, due_at)
                VALUES ('lives_refill:' || $1::bigint::text, $1, 'lives_refill', $2)
                ON CONFLICT (dedupe_key) DO UPDATE SET
                    due_at=EXCLUDED.due_at, status='pending', locked_at=NULL,
                    last_error=NULL, updated_at=now()
                """,
                user_id, due_at,
            )
            return due_at.isoformat()
