"""School-configured Telegram keyboards for diagnostic navigation."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from diagnostic.school import SchoolConfig


def tracked_url(url: object, user_id: int, content: str) -> str:
    """Add generic diagnostic attribution without changing school ownership."""
    del user_id
    parts = urlsplit(str(url))
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update(
        {
            "utm_source": "telegram",
            "utm_medium": "bot",
            "utm_campaign": "diagnostic",
            "utm_content": content,
        }
    )
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def webapp_keyboard(
    school: SchoolConfig,
    miniapp_url: str,
    *,
    label: str | None = None,
) -> InlineKeyboardMarkup:
    button_label = label or school.brand.interface.start_diagnostic
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=button_label, web_app=WebAppInfo(url=miniapp_url))]
        ]
    )


def _offer_rows(school: SchoolConfig, user_id: int) -> list[list[InlineKeyboardButton]]:
    return [
        [
            InlineKeyboardButton(
                text=offer.button,
                url=tracked_url(offer.url, user_id, offer.id),
            )
        ]
        for offer in school.links.offers
    ]


def home_keyboard(
    school: SchoolConfig,
    miniapp_url: str,
    user_id: int,
) -> InlineKeyboardMarkup:
    labels = school.brand.interface
    rows = [
        [InlineKeyboardButton(text=labels.open_diagnostic, web_app=WebAppInfo(url=miniapp_url))],
        [
            InlineKeyboardButton(text=labels.results, callback_data="diag:results"),
            InlineKeyboardButton(text=labels.plan, callback_data="diag:plan"),
        ],
    ]
    rows.extend(_offer_rows(school, user_id))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def result_keyboard(
    school: SchoolConfig,
    user_id: int,
    attempt_id: str,
    mode: str,
    *,
    miniapp_url: str | None = None,
) -> InlineKeyboardMarkup:
    labels = school.brand.interface
    rows = _offer_rows(school, user_id)
    rows.append(
        [
            InlineKeyboardButton(text=labels.plan, callback_data="diag:plan"),
            InlineKeyboardButton(text=labels.results, callback_data="diag:results"),
        ]
    )
    if miniapp_url:
        label = (
            labels.take_full_diagnostic
            if mode == "quick"
            else labels.check_another_subject
        )
        rows.append(
            [InlineKeyboardButton(text=label, web_app=WebAppInfo(url=miniapp_url))]
        )
    rows.append([InlineKeyboardButton(text=labels.home, callback_data="diag:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _value(row: Mapping[str, Any], key: str, default: Any = None) -> Any:
    try:
        value = row[key]
    except (KeyError, TypeError):
        value = default
    return default if value is None else value


def _button_text(value: object) -> str:
    return str(value)[:64]


def results_keyboard(
    school: SchoolConfig,
    rows: list[Mapping[str, Any]],
    miniapp_url: str,
    *,
    timezone_name: str = "UTC",
) -> InlineKeyboardMarkup:
    labels = school.brand.interface
    buttons: list[list[InlineKeyboardButton]] = []
    for row in rows:
        completed_at = _value(row, "completed_at")
        if isinstance(completed_at, datetime):
            aware = completed_at if completed_at.tzinfo else completed_at.replace(tzinfo=timezone.utc)
            try:
                date_label = aware.astimezone(ZoneInfo(timezone_name)).strftime("%d.%m")
            except (KeyError, ValueError):
                date_label = labels.ready_result
        else:
            date_label = labels.ready_result
        mode_label = (
            labels.quick_result
            if _value(row, "mode", "quick") == "quick"
            else labels.full_result
        )
        buttons.append(
            [
                InlineKeyboardButton(
                    text=_button_text(
                        f"{_value(row, 'subject', '')} · {mode_label} · {date_label}"
                    ),
                    callback_data=f"diag:result:{_value(row, 'attempt_id', '')}",
                )
            ]
        )
    buttons.extend(
        [
            [
                InlineKeyboardButton(
                    text=labels.take_another_diagnostic,
                    web_app=WebAppInfo(url=miniapp_url),
                )
            ],
            [InlineKeyboardButton(text=labels.home, callback_data="diag:menu")],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)
