"""Connection-pool lifecycle for the starter's diagnostic database."""

from __future__ import annotations

import asyncio
import json

import asyncpg

from diagnostic.db.schema import DDL

_pool: asyncpg.Pool | None = None


async def _init_connection(connection: asyncpg.Connection) -> None:
    await connection.set_type_codec(
        "jsonb",
        schema="pg_catalog",
        encoder=json.dumps,
        decoder=json.loads,
        format="text",
    )


async def init_db(database_url: str, school=None) -> None:
    """Create the pool, schema, and editable message defaults."""
    global _pool
    if _pool is not None:
        await _pool.close()
    _pool = await asyncpg.create_pool(
        database_url,
        min_size=1,
        max_size=10,
        init=_init_connection,
    )
    async with _pool.acquire() as connection:
        async with connection.transaction():
            await connection.execute(
                "SELECT pg_advisory_xact_lock($1)", 6_421_993_071_113_001
            )
            await connection.execute(DDL)
            from diagnostic.db.messages import seed_messages
            if school is None:
                from diagnostic.school import load_school

                school = load_school()

            await seed_messages(connection, school)


async def close_db() -> None:
    """Close the pool when the application shuts down."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("database_not_initialized")
    return _pool


async def database_ready(timeout_seconds: float = 2.0) -> bool:
    try:
        pool = await get_pool()

        async def probe() -> bool:
            async with pool.acquire() as connection:
                return await connection.fetchval("SELECT 1") == 1

        return await asyncio.wait_for(probe(), timeout=timeout_seconds)
    except (RuntimeError, asyncpg.PostgresError, OSError, asyncio.TimeoutError):
        return False
