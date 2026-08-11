from __future__ import annotations

from unittest.mock import AsyncMock

import pytest


class _Context:
    def __init__(self, value, connection=None):
        self.value = value
        self.connection = connection

    async def __aenter__(self):
        if self.connection is not None:
            self.connection.in_transaction = True
        return self.value

    async def __aexit__(self, *_):
        if self.connection is not None:
            self.connection.in_transaction = False


class _Connection:
    def __init__(self):
        self.operations: list[tuple[str, str, bool]] = []
        self.in_transaction = False

    def transaction(self):
        return _Context(self, self)

    async def execute(self, sql, *_):
        self.operations.append(("execute", " ".join(sql.split()), self.in_transaction))

    async def fetchrow(self, sql, *_):
        self.operations.append(("fetchrow", " ".join(sql.split()), self.in_transaction))
        return None

    async def fetch(self, sql, *_):
        self.operations.append(("fetch", " ".join(sql.split()), self.in_transaction))
        return []


class _Pool:
    def __init__(self, connection):
        self.connection = connection

    def acquire(self):
        return _Context(self.connection)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("claim_name", "attempts_column", "status_column", "lock_column", "select_operation"),
    [
        ("claim_pending_pdf", "pdf_attempts", "pdf_status", "pdf_locked_at", "fetchrow"),
        ("claim_due_notifications", "attempts", "status", "locked_at", "fetch"),
    ],
)
async def test_claim_tick_atomically_abandons_only_stale_exhausted_sending_leases(
    monkeypatch,
    claim_name,
    attempts_column,
    status_column,
    lock_column,
    select_operation,
):
    from diagnostic.db import attempts

    connection = _Connection()
    monkeypatch.setattr(attempts, "get_pool", AsyncMock(return_value=_Pool(connection)))

    result = await getattr(attempts, claim_name)()

    assert result is None or result == []
    assert [operation[0] for operation in connection.operations] == ["execute", select_operation]
    cleanup = connection.operations[0][1]
    selection = connection.operations[1][1]
    assert connection.operations[0][2] is True
    assert connection.operations[1][2] is True
    assert f"SET {status_column}='abandoned'" in cleanup
    assert f"{status_column}='sending'" in cleanup
    assert f"{attempts_column} >= 8" in cleanup
    assert f"{lock_column} <= now() - interval '10 minutes'" in cleanup
    assert f"{lock_column}=NULL" in cleanup
    assert "retry_limit_reached" in cleanup
    assert f"{attempts_column} < 8" in selection
