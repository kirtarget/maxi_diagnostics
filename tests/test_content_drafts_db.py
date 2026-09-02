from __future__ import annotations

from copy import deepcopy
from unittest.mock import AsyncMock

import pytest

from diagnostic.db import content


class _Context:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, *_):
        return None


class _Connection:
    def __init__(self, current):
        self.current = current
        self.fetchrow_calls = []
        self.execute_calls = []

    def transaction(self):
        return _Context(self)

    async def fetchrow(self, sql, *arguments):
        normalized = " ".join(sql.split())
        self.fetchrow_calls.append((normalized, arguments))
        if normalized.startswith("SELECT diagnostic_id"):
            return deepcopy(self.current)
        if normalized.startswith("UPDATE diagnostic_content_drafts"):
            self.current = {
                **self.current,
                "payload": deepcopy(arguments[1]),
                "edit_revision": arguments[2],
                "payload_sha256": arguments[3],
                "updated_by": arguments[4],
            }
            return deepcopy(self.current)
        raise AssertionError(normalized)

    async def execute(self, sql, *arguments):
        self.execute_calls.append((" ".join(sql.split()), arguments))
        return "INSERT 0 1"


class _Pool:
    def __init__(self, connection):
        self.connection = connection

    def acquire(self):
        return _Context(self.connection)


def row(payload, revision=3):
    return {
        "diagnostic_id": "demo-math",
        "payload": deepcopy(payload),
        "edit_revision": revision,
        "base_content_version": "a" * 64,
        "payload_sha256": content.payload_sha256(payload),
        "updated_by": "admin",
        "updated_at": None,
    }


@pytest.mark.asyncio
async def test_same_payload_retry_is_idempotent_even_with_stale_revision(monkeypatch):
    payload = {"id": "demo-math", "questions": [{"id": "q1", "correct": ["private"]}]}
    connection = _Connection(row(payload, revision=3))
    monkeypatch.setattr(content, "get_pool", AsyncMock(return_value=_Pool(connection)))

    result = await content.save_draft(
        diagnostic_id="demo-math",
        payload=payload,
        expected_revision=2,
        actor="admin",
        action="question_updated",
        question_id="q1",
    )

    assert result["edit_revision"] == 3
    assert connection.execute_calls == []
    assert not any(call[0].startswith("UPDATE") for call in connection.fetchrow_calls)


@pytest.mark.asyncio
async def test_changed_payload_rejects_stale_revision_without_audit(monkeypatch):
    original = {"id": "demo-math", "questions": [{"id": "q1", "correct": ["private"]}]}
    changed = {"id": "demo-math", "questions": [{"id": "q1", "correct": ["changed"]}]}
    connection = _Connection(row(original, revision=4))
    monkeypatch.setattr(content, "get_pool", AsyncMock(return_value=_Pool(connection)))

    with pytest.raises(content.ContentRevisionConflict):
        await content.save_draft(
            diagnostic_id="demo-math",
            payload=changed,
            expected_revision=3,
            actor="admin",
            action="question_updated",
            question_id="q1",
        )

    assert connection.execute_calls == []


@pytest.mark.asyncio
async def test_successful_update_increments_revision_and_audits_only_hashes(monkeypatch):
    original = {"id": "demo-math", "questions": [{"id": "q1", "correct": ["private-answer"]}]}
    changed = {"id": "demo-math", "questions": [{"id": "q1", "correct": ["new-private-answer"]}]}
    connection = _Connection(row(original, revision=5))
    monkeypatch.setattr(content, "get_pool", AsyncMock(return_value=_Pool(connection)))

    result = await content.save_draft(
        diagnostic_id="demo-math",
        payload=changed,
        expected_revision=5,
        actor="admin",
        action="question_updated",
        question_id="q1",
    )

    assert result["edit_revision"] == 6
    assert len(connection.execute_calls) == 1
    audit_sql, audit_arguments = connection.execute_calls[0]
    assert audit_sql.startswith("INSERT INTO diagnostic_content_audit")
    assert audit_arguments[:5] == ("question_updated", "admin", "demo-math", "q1", 6)
    assert all("private-answer" not in str(value) for value in audit_arguments)
    assert len(audit_arguments[5]) == len(audit_arguments[6]) == 64


def test_canonical_payload_is_stable_utf8_without_bom():
    left = {"тема": "Алгебра", "id": "q1"}
    right = {"id": "q1", "тема": "Алгебра"}

    assert content.canonical_payload(left) == content.canonical_payload(right)
    assert content.canonical_payload(left).startswith(b'{"id"')
    assert not content.canonical_payload(left).startswith(b"\xef\xbb\xbf")
