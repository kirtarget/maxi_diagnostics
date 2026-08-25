"""Transactional persistence for the server-owned trainer loop."""

from __future__ import annotations

from datetime import datetime, timezone
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
        "question_ids": list(selected),
        "current_index": int(row["current_index"]),
        "revision": int(row["revision"]),
        "status": row["status"],
    }


def _answer_payload(
    answer_row: Mapping[str, Any], session_row: Mapping[str, Any], profile: Mapping[str, Any]
) -> dict[str, Any]:
    feedback = answer_row["public_feedback"] or {}
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
        "lives_remaining": int(profile["lives_remaining"]),
    }


async def _locked_session(connection, session_id: str, user_id: int):
    return await connection.fetchrow(
        """
        SELECT session_id, user_id, diagnostic_id, content_version, mode,
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
                   selected_question_ids, current_index, revision, status,
                   started_at, updated_at, completed_at
              FROM diagnostic_trainer_sessions
             WHERE session_id=$1 AND user_id=$2
            """,
            session_id,
            user_id,
        )


async def start_session(
    *, session_id: str, user_id: int, diagnostic_id: str, content_version: str,
    mode: str, selected_question_ids: list[str],
) -> tuple[dict[str, Any], Mapping[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as connection:
        async with connection.transaction():
            await connection.execute("SELECT pg_advisory_xact_lock($1)", user_id)
            await _raise_if_erased(connection, user_id)
            profile = await gameplay.get_reconciled_profile(connection, user_id)
            row = await connection.fetchrow(
                """
                INSERT INTO diagnostic_trainer_sessions (
                    session_id, user_id, diagnostic_id, content_version, mode,
                    selected_question_ids
                ) VALUES ($1,$2,$3,$4,$5,$6::jsonb)
                RETURNING session_id, diagnostic_id, content_version, mode,
                          selected_question_ids, current_index, revision, status,
                          started_at, updated_at, completed_at
                """,
                session_id,
                user_id,
                diagnostic_id,
                content_version,
                mode,
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
            if not is_correct and int(profile["lives_remaining"]) <= 0:
                raise ValueError("trainer_no_lives")

            xp_delta = 10 if is_correct else 0
            life_delta = 0 if is_correct else -1
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
            if is_correct:
                await gameplay.apply_gameplay_event(
                    connection,
                    gameplay.build_trainer_answer_event(
                        user_id=user_id,
                        session_id=session_id,
                        question_id=question_id,
                        timezone_name=timezone_name,
                    ),
                )
            else:
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

            next_index = current_index + 1
            next_status = "exhausted" if next_index >= len(selected) else "active"
            session = await connection.fetchrow(
                """
                UPDATE diagnostic_trainer_sessions
                   SET current_index=$2, revision=$3, status=$4, updated_at=now()
                 WHERE session_id=$1
                 RETURNING session_id, diagnostic_id, content_version, mode,
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
