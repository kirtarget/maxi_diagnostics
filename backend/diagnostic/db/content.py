"""Private content drafts with optimistic revisions and metadata-only audit."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any, Literal

from diagnostic.db.core import get_pool


ContentAction = Literal[
    "draft_created", "question_created", "question_updated", "validated", "exported"
]


class ContentDraftNotFound(RuntimeError):
    pass


class ContentRevisionConflict(RuntimeError):
    pass


def canonical_payload(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def payload_sha256(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_payload(payload)).hexdigest()


async def _audit(
    connection,
    *,
    action: ContentAction,
    actor: str,
    diagnostic_id: str,
    question_id: str | None,
    edit_revision: int,
    before_hash: str,
    after_hash: str,
) -> None:
    await connection.execute(
        """
        INSERT INTO diagnostic_content_audit (
            action, actor, diagnostic_id, question_id, edit_revision,
            before_hash, after_hash
        ) VALUES ($1,$2,$3,$4,$5,$6,$7)
        """,
        action,
        actor,
        diagnostic_id,
        question_id,
        edit_revision,
        before_hash,
        after_hash,
    )


async def list_drafts() -> list:
    pool = await get_pool()
    async with pool.acquire() as connection:
        return list(
            await connection.fetch(
                """
                SELECT diagnostic_id, payload, edit_revision, base_content_version,
                       payload_sha256, updated_by, updated_at
                  FROM diagnostic_content_drafts
                 ORDER BY diagnostic_id
                """
            )
        )


async def get_draft(diagnostic_id: str):
    pool = await get_pool()
    async with pool.acquire() as connection:
        return await connection.fetchrow(
            """
            SELECT diagnostic_id, payload, edit_revision, base_content_version,
                   payload_sha256, updated_by, updated_at
              FROM diagnostic_content_drafts
             WHERE diagnostic_id=$1
            """,
            diagnostic_id,
        )


async def create_draft(
    *,
    diagnostic_id: str,
    payload: Mapping[str, Any],
    base_content_version: str,
    actor: str,
):
    digest = payload_sha256(payload)
    pool = await get_pool()
    async with pool.acquire() as connection:
        async with connection.transaction():
            row = await connection.fetchrow(
                """
                INSERT INTO diagnostic_content_drafts (
                    diagnostic_id, payload, edit_revision, base_content_version,
                    payload_sha256, created_by, updated_by
                ) VALUES ($1,$2,1,$3,$4,$5,$5)
                ON CONFLICT (diagnostic_id) DO NOTHING
                RETURNING diagnostic_id, payload, edit_revision, base_content_version,
                          payload_sha256, updated_by, updated_at
                """,
                diagnostic_id,
                dict(payload),
                base_content_version,
                digest,
                actor,
            )
            if row is not None:
                await _audit(
                    connection,
                    action="draft_created",
                    actor=actor,
                    diagnostic_id=diagnostic_id,
                    question_id=None,
                    edit_revision=1,
                    before_hash=digest,
                    after_hash=digest,
                )
                return row
            return await connection.fetchrow(
                """
                SELECT diagnostic_id, payload, edit_revision, base_content_version,
                       payload_sha256, updated_by, updated_at
                  FROM diagnostic_content_drafts
                 WHERE diagnostic_id=$1
                """,
                diagnostic_id,
            )


async def save_draft(
    *,
    diagnostic_id: str,
    payload: Mapping[str, Any],
    expected_revision: int,
    actor: str,
    action: Literal["question_created", "question_updated"],
    question_id: str,
):
    digest = payload_sha256(payload)
    pool = await get_pool()
    async with pool.acquire() as connection:
        async with connection.transaction():
            current = await connection.fetchrow(
                """
                SELECT diagnostic_id, payload, edit_revision, base_content_version,
                       payload_sha256, updated_by, updated_at
                  FROM diagnostic_content_drafts
                 WHERE diagnostic_id=$1
                 FOR UPDATE
                """,
                diagnostic_id,
            )
            if current is None:
                raise ContentDraftNotFound("content_draft_not_found")
            if current["payload_sha256"] == digest:
                return current
            if current["edit_revision"] != expected_revision:
                raise ContentRevisionConflict("content_revision_conflict")
            next_revision = expected_revision + 1
            row = await connection.fetchrow(
                """
                UPDATE diagnostic_content_drafts
                   SET payload=$2, edit_revision=$3, payload_sha256=$4,
                       updated_by=$5, updated_at=now()
                 WHERE diagnostic_id=$1
                RETURNING diagnostic_id, payload, edit_revision, base_content_version,
                          payload_sha256, updated_by, updated_at
                """,
                diagnostic_id,
                dict(payload),
                next_revision,
                digest,
                actor,
            )
            await _audit(
                connection,
                action=action,
                actor=actor,
                diagnostic_id=diagnostic_id,
                question_id=question_id,
                edit_revision=next_revision,
                before_hash=current["payload_sha256"],
                after_hash=digest,
            )
            return row


async def record_action(
    *,
    diagnostic_id: str,
    expected_revision: int,
    actor: str,
    action: Literal["validated", "exported"],
):
    pool = await get_pool()
    async with pool.acquire() as connection:
        async with connection.transaction():
            current = await connection.fetchrow(
                """
                SELECT diagnostic_id, payload, edit_revision, base_content_version,
                       payload_sha256, updated_by, updated_at
                  FROM diagnostic_content_drafts
                 WHERE diagnostic_id=$1
                 FOR SHARE
                """,
                diagnostic_id,
            )
            if current is None:
                raise ContentDraftNotFound("content_draft_not_found")
            if current["edit_revision"] != expected_revision:
                raise ContentRevisionConflict("content_revision_conflict")
            await _audit(
                connection,
                action=action,
                actor=actor,
                diagnostic_id=diagnostic_id,
                question_id=None,
                edit_revision=expected_revision,
                before_hash=current["payload_sha256"],
                after_hash=current["payload_sha256"],
            )
            return current
