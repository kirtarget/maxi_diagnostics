"""Persistent Telegram file IDs for reusable school message images."""

from __future__ import annotations

from diagnostic.db.core import get_pool


async def get_telegram_file_id(
    school_id: str, message_key: str, asset_sha256: str
) -> str | None:
    pool = await get_pool()
    async with pool.acquire() as connection:
        value = await connection.fetchval(
            """
            SELECT telegram_file_id
              FROM message_media_cache
             WHERE school_id=$1 AND message_key=$2 AND asset_sha256=$3
            """,
            school_id,
            message_key,
            asset_sha256,
        )
    return str(value) if value else None


async def save_telegram_file_id(
    school_id: str,
    message_key: str,
    asset_sha256: str,
    telegram_file_id: str,
) -> None:
    if not telegram_file_id or len(telegram_file_id) > 512:
        return
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute(
            """
            INSERT INTO message_media_cache (
                school_id, message_key, asset_sha256, telegram_file_id
            )
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (school_id, message_key) DO UPDATE
               SET asset_sha256=EXCLUDED.asset_sha256,
                   telegram_file_id=EXCLUDED.telegram_file_id,
                   updated_at=now()
            """,
            school_id,
            message_key,
            asset_sha256,
            telegram_file_id,
        )
