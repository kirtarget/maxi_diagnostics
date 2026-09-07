from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.types import FSInputFile

from diagnostic.school import load_school


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.asyncio
async def test_sender_uploads_configured_photo_and_saves_file_id(monkeypatch):
    from diagnostic.bot import sender

    school = load_school(ROOT / "school")
    monkeypatch.setattr(
        sender.message_media, "get_telegram_file_id", AsyncMock(return_value=None)
    )
    save_file_id = AsyncMock()
    monkeypatch.setattr(sender.message_media, "save_telegram_file_id", save_file_id)
    send_text = AsyncMock()
    send_photo = AsyncMock(
        return_value=SimpleNamespace(
            message_id=41,
            photo=[SimpleNamespace(file_id="telegram-photo-id")],
        )
    )

    result = await sender.send_school_message(
        send_text=send_text,
        send_photo=send_photo,
        school=school,
        message_key="WELCOME",
        text="Привет 👋",
        reply_markup="keyboard",
    )
    await asyncio.sleep(0)

    assert result.message_id == 41
    send_text.assert_not_awaited()
    assert isinstance(send_photo.await_args.args[0], FSInputFile)
    assert send_photo.await_args.kwargs["caption"] == "Привет 👋"
    assert save_file_id.await_args.args[3] == "telegram-photo-id"


@pytest.mark.asyncio
async def test_sender_reuses_cached_file_id(monkeypatch):
    from diagnostic.bot import sender

    school = load_school(ROOT / "school")
    monkeypatch.setattr(
        sender.message_media,
        "get_telegram_file_id",
        AsyncMock(return_value="cached-photo-id"),
    )
    send_photo = AsyncMock(return_value=SimpleNamespace(message_id=42, photo=[]))

    await sender.send_school_message(
        send_text=AsyncMock(),
        send_photo=send_photo,
        school=school,
        message_key="WELCOME",
        text="Привет 👋",
    )

    assert send_photo.await_args.args[0] == "cached-photo-id"


@pytest.mark.asyncio
async def test_sender_falls_back_to_text_above_caption_limit(monkeypatch):
    from diagnostic.bot import sender

    school = load_school(ROOT / "school")
    get_file_id = AsyncMock()
    monkeypatch.setattr(sender.message_media, "get_telegram_file_id", get_file_id)
    send_text = AsyncMock()
    send_photo = AsyncMock()
    text = "а" * 1025

    await sender.send_school_message(
        send_text=send_text,
        send_photo=send_photo,
        school=school,
        message_key="WELCOME",
        text=text,
    )

    send_text.assert_awaited_once()
    send_photo.assert_not_awaited()
    get_file_id.assert_not_awaited()
