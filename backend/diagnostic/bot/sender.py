"""Single-message Telegram sender with optional school-owned artwork."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections.abc import Awaitable, Callable
from functools import lru_cache
from pathlib import Path
from typing import Any

from aiogram.types import FSInputFile

from diagnostic.db import message_media
from diagnostic.school import SchoolConfig


logger = logging.getLogger(__name__)
Sender = Callable[..., Awaitable[Any]]


@lru_cache(maxsize=32)
def _asset_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _telegram_file_id(message: Any) -> str | None:
    photos = getattr(message, "photo", None)
    if not photos:
        return None
    file_id = getattr(photos[-1], "file_id", None)
    return file_id if isinstance(file_id, str) and 0 < len(file_id) <= 512 else None


async def _photo_source(
    school: SchoolConfig, message_key: str
) -> tuple[str | FSInputFile, str] | None:
    relative_path = school.brand.message_images.keyed().get(message_key)
    if relative_path is None:
        return None
    path = school.resolve_asset(relative_path)
    asset_sha256 = _asset_sha256(path)
    try:
        cached = await message_media.get_telegram_file_id(
            school.brand.school_id, message_key, asset_sha256
        )
    except Exception:
        logger.warning("message_media_cache_read_failed")
        cached = None
    return (cached or FSInputFile(path), asset_sha256)


async def _save_file_id_safely(
    school_id: str, message_key: str, asset_sha256: str, file_id: str
) -> None:
    try:
        await message_media.save_telegram_file_id(
            school_id, message_key, asset_sha256, file_id
        )
    except Exception:
        logger.warning("message_media_cache_write_failed")


async def send_school_message(
    *,
    send_text: Sender,
    send_photo: Sender | None,
    school: SchoolConfig,
    message_key: str,
    text: str,
    reply_markup: Any = None,
) -> Any:
    """Send one text or one photo-caption message for an internal message key."""
    text_kwargs: dict[str, Any] = {
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup is not None:
        text_kwargs["reply_markup"] = reply_markup

    if send_photo is None or len(text) > 1024:
        return await send_text(text, **text_kwargs)

    source = await _photo_source(school, message_key)
    if source is None:
        return await send_text(text, **text_kwargs)

    photo, asset_sha256 = source
    photo_kwargs: dict[str, Any] = {"caption": text, "parse_mode": "HTML"}
    if reply_markup is not None:
        photo_kwargs["reply_markup"] = reply_markup
    message = await send_photo(photo, **photo_kwargs)

    if isinstance(photo, FSInputFile):
        file_id = _telegram_file_id(message)
        if file_id is not None:
            asyncio.create_task(
                _save_file_id_safely(
                    school.brand.school_id, message_key, asset_sha256, file_id
                )
            )
    return message
