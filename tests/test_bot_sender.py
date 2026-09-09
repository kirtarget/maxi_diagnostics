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
async def test_sender_uploads_configured_photo_and_saves_telegram_file_id(monkeypatch):
    from diagnostic.bot import sender

    school = load_school(ROOT / "school")
    get_file_id = AsyncMock(return_value=None)
    save_file_id = AsyncMock()
    monkeypatch.setattr(sender.message_media, "get_telegram_file_id", get_file_id)
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
    photo = send_photo.await_args.args[0]
    assert isinstance(photo, FSInputFile)
    assert Path(photo.path) == school.resolve_asset("assets/messages/welcome.png")
    assert send_photo.await_args.kwargs == {
        "caption": "Привет 👋",
        "parse_mode": "HTML",
        "reply_markup": "keyboard",
    }
    save_args = save_file_id.await_args.args
    assert save_args[0:2] == (school.brand.school_id, "WELCOME")
    assert len(save_args[2]) == 64
    assert save_args[3] == "telegram-photo-id"


@pytest.mark.asyncio
async def test_sender_reuses_cached_telegram_file_id(monkeypatch):
    from diagnostic.bot import sender

    school = load_school(ROOT / "school")
    monkeypatch.setattr(
        sender.message_media,
        "get_telegram_file_id",
        AsyncMock(return_value="cached-photo-id"),
    )
    save_file_id = AsyncMock()
    monkeypatch.setattr(sender.message_media, "save_telegram_file_id", save_file_id)
    send_photo = AsyncMock(return_value=SimpleNamespace(message_id=42, photo=[]))

    await sender.send_school_message(
        send_text=AsyncMock(),
        send_photo=send_photo,
        school=school,
        message_key="WELCOME",
        text="Привет 👋",
    )

    assert send_photo.await_args.args[0] == "cached-photo-id"
    save_file_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_sender_returns_before_background_file_id_cache_write(monkeypatch):
    from diagnostic.bot import sender

    school = load_school(ROOT / "school")
    monkeypatch.setattr(
        sender.message_media, "get_telegram_file_id", AsyncMock(return_value=None)
    )
    cache_started = asyncio.Event()
    release_cache = asyncio.Event()

    async def slow_cache_write(*_args):
        cache_started.set()
        await release_cache.wait()

    monkeypatch.setattr(
        sender.message_media, "save_telegram_file_id", slow_cache_write
    )
    send_photo = AsyncMock(
        return_value=SimpleNamespace(
            message_id=45,
            photo=[SimpleNamespace(file_id="telegram-photo-id")],
        )
    )

    result = await asyncio.wait_for(
        sender.send_school_message(
            send_text=AsyncMock(),
            send_photo=send_photo,
            school=school,
            message_key="WELCOME",
            text="Привет 👋",
        ),
        timeout=1,
    )

    assert result.message_id == 45
    await asyncio.wait_for(cache_started.wait(), timeout=1)
    release_cache.set()
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_sender_keeps_one_text_message_when_caption_is_too_long(monkeypatch):
    from diagnostic.bot import sender

    school = load_school(ROOT / "school")
    get_file_id = AsyncMock()
    monkeypatch.setattr(sender.message_media, "get_telegram_file_id", get_file_id)
    send_text = AsyncMock(return_value=SimpleNamespace(message_id=43))
    send_photo = AsyncMock()
    text = "а" * 1025

    await sender.send_school_message(
        send_text=send_text,
        send_photo=send_photo,
        school=school,
        message_key="WELCOME",
        text=text,
    )

    send_text.assert_awaited_once_with(
        text, parse_mode="HTML", disable_web_page_preview=True
    )
    send_photo.assert_not_awaited()
    get_file_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_sender_uses_text_for_unillustrated_message(monkeypatch):
    from diagnostic.bot import sender

    school = load_school(ROOT / "school")
    get_file_id = AsyncMock()
    monkeypatch.setattr(sender.message_media, "get_telegram_file_id", get_file_id)
    send_text = AsyncMock(return_value=SimpleNamespace(message_id=44))

    await sender.send_school_message(
        send_text=send_text,
        send_photo=AsyncMock(),
        school=school,
        message_key="DATA_ERASED",
        text="Данные удалены 🧹",
    )

    send_text.assert_awaited_once()
    get_file_id.assert_not_awaited()
