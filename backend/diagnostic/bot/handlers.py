"""Stateless Aiogram handlers for the diagnostic-only bot."""

from __future__ import annotations

import html
from collections.abc import Mapping
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from diagnostic.analytics import fire_event
from diagnostic.catalog import DiagnosticCatalog
from diagnostic.db import attempts, funnel
from diagnostic.messages import render_message
from diagnostic.school import SchoolConfig
from diagnostic.score_text import estimate_caption, estimate_headline
from diagnostic.settings import Settings

from .keyboards import home_keyboard, result_keyboard, results_keyboard, webapp_keyboard


def _value(row: Mapping[str, Any], key: str, default: Any = None) -> Any:
    try:
        value = row[key]
    except (KeyError, TypeError):
        value = default
    return default if value is None else value


def _estimate(row: Mapping[str, Any]) -> Any:
    snapshot = _value(row, "result_snapshot")
    return snapshot.get("estimate") if isinstance(snapshot, Mapping) else None


def _diagnostic_value(
    row: Mapping[str, Any], catalog: DiagnosticCatalog, field: str, default: str
) -> str:
    value = _value(row, field)
    if value:
        return str(value)
    diagnostic_id = _value(row, "diagnostic_id")
    if diagnostic_id:
        try:
            return str(getattr(catalog.get(str(diagnostic_id)), field))
        except ValueError:
            pass
    return default


async def _mark_viewed(attempt_id: str, user_id: int, settings: Settings) -> None:
    try:
        row = await attempts.mark_result_viewed(attempt_id, user_id)
    except (RuntimeError, ValueError):
        return
    if _value(row, "viewed_transition", False):
        fire_event(
            "diagnostic_result_viewed", user_id, {"attempt_id": attempt_id}
        )
        await funnel.record_event(
            application_secret=settings.application_secret,
            user_id=user_id,
            action="result_viewed",
            exam=_value(row, "exam"),
            subject=_value(row, "subject"),
        )


async def send_home(
    message: Message,
    settings: Settings,
    school: SchoolConfig,
    catalog: DiagnosticCatalog,
) -> None:
    del catalog
    user_id = message.from_user.id
    try:
        first_open = await attempts.mark_opened(user_id)
    except ValueError as exc:
        if str(exc) != "diagnostic_user_erased":
            raise
        await message.answer(
            await render_message("DATA_ERASED", school),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        return
    if first_open:
        fire_event("diagnostic_opened", user_id, {})
        await funnel.record_event(
            application_secret=settings.application_secret,
            user_id=user_id,
            action="opened",
        )
    text = await render_message("WELCOME", school)
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=home_keyboard(school, settings.miniapp_url, user_id),
        disable_web_page_preview=True,
    )


async def send_results(
    message: Message,
    settings: Settings,
    school: SchoolConfig,
    catalog: DiagnosticCatalog,
) -> None:
    await _send_results_to(
        message.answer,
        message.from_user.id,
        settings,
        school,
        catalog,
    )


async def _send_results_to(answer, user_id: int, settings, school, catalog) -> None:
    rows = list(await attempts.list_completed_attempts(user_id))
    if not rows:
        text = await render_message("RESULTS_EMPTY", school)
        await answer(
            text,
            parse_mode="HTML",
            reply_markup=webapp_keyboard(school, settings.miniapp_url),
            disable_web_page_preview=True,
        )
        return

    interface = school.brand.interface
    fallback = interface.diagnostic_fallback
    lines = [f"<b>{html.escape(interface.results_heading, quote=True)}</b>", ""]
    for row in rows[:10]:
        subject = html.escape(_diagnostic_value(row, catalog, "subject", fallback), quote=True)
        score = html.escape(str(_value(row, "score", 0)), quote=True)
        score_suffix = "%" if _value(row, "score_unit") == "accuracy_percent" else ""
        headline = estimate_headline(_estimate(row), _value(row, "exam", ""))
        estimate_part = (
            f" · {html.escape(headline, quote=True)}" if headline is not None else ""
        )
        mode = (
            interface.quick_result
            if _value(row, "mode", "quick") == "quick"
            else interface.full_result
        )
        mode = html.escape(mode, quote=True)
        lines.append(
            f"• <b>{subject}</b> — {score}{score_suffix}{estimate_part} ({mode})"
        )
    await answer(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=results_keyboard(
            school, rows[:10], settings.miniapp_url,
            timezone_name=settings.timezone,
        ),
        disable_web_page_preview=True,
    )
    for row in rows[:10]:
        await _mark_viewed(str(_value(row, "attempt_id", "")), user_id, settings)


async def send_plan(
    message: Message,
    settings: Settings,
    school: SchoolConfig,
    catalog: DiagnosticCatalog,
) -> None:
    await _send_plan_to(
        message.answer,
        message.from_user.id,
        settings,
        school,
        catalog,
    )


async def _send_plan_to(answer, user_id: int, settings, school, catalog) -> None:
    rows = list(await attempts.list_completed_attempts(user_id))
    if not rows:
        text = await render_message("PLAN_EMPTY", school)
        await answer(
            text,
            parse_mode="HTML",
            reply_markup=webapp_keyboard(school, settings.miniapp_url),
            disable_web_page_preview=True,
        )
        return

    latest = rows[0]
    interface = school.brand.interface
    subject = html.escape(
        _diagnostic_value(latest, catalog, "subject", interface.diagnostic_fallback),
        quote=True,
    )
    strong = [html.escape(str(topic), quote=True) for topic in (_value(latest, "strong_topics", []) or [])]
    growth = [html.escape(str(topic), quote=True) for topic in (_value(latest, "growth_topics", []) or [])]
    lines = [f"<b>{html.escape(interface.plan_for, quote=True)} {subject}</b>"]
    if strong:
        lines.extend([
            "",
            f"<b>{html.escape(interface.keep_strong, quote=True)}:</b>",
            *(f"✓ {topic}" for topic in strong),
        ])
    if growth:
        lines.extend(
            [
                "",
                f"<b>{html.escape(interface.focus_next, quote=True)}:</b>",
                *(f"{index}. {topic}" for index, topic in enumerate(growth, 1)),
            ]
        )
    if not strong and not growth:
        lines.extend(["", html.escape(interface.open_result_hint, quote=True)])
    await answer(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=result_keyboard(
            school,
            user_id,
            str(_value(latest, "attempt_id", "")),
            str(_value(latest, "mode", "full")),
            miniapp_url=settings.miniapp_url,
        ),
        disable_web_page_preview=True,
    )
    await _mark_viewed(str(_value(latest, "attempt_id", "")), user_id, settings)


async def show_result(
    callback: CallbackQuery,
    settings: Settings,
    school: SchoolConfig,
    catalog: DiagnosticCatalog,
) -> None:
    data = callback.data or ""
    attempt_id = data.removeprefix("diag:result:") if data.startswith("diag:result:") else ""
    if not attempt_id:
        await callback.answer(school.brand.interface.result_not_found, show_alert=True)
        return
    user_id = callback.from_user.id
    attempt = await attempts.get_attempt(attempt_id, user_id)
    if not attempt or _value(attempt, "status") != "completed":
        await callback.answer(school.brand.interface.result_not_found, show_alert=True)
        return

    await callback.answer()
    subject = html.escape(
        _diagnostic_value(
            attempt, catalog, "subject", school.brand.interface.diagnostic_fallback
        ),
        quote=True,
    )
    score = html.escape(str(_value(attempt, "score", 0)), quote=True)
    question_count = html.escape(str(_value(attempt, "question_count", 0)), quote=True)
    correct_count = html.escape(str(_value(attempt, "correct_count", 0)), quote=True)
    estimate = _estimate(attempt)
    headline = estimate_headline(estimate, _value(attempt, "exam", ""))
    caption = estimate_caption(estimate)
    estimate_lines = (
        f"<b>{html.escape(headline, quote=True)}</b>\n"
        f"{html.escape(caption, quote=True)}\n"
        if headline is not None and caption is not None else ""
    )
    if callback.message:
        await callback.message.answer(
            f"<b>{subject}</b>\n"
            f"{estimate_lines}"
            f"{html.escape(school.brand.pdf.score_label, quote=True)}: {score}\n"
            f"{html.escape(school.brand.pdf.correct_label, quote=True)}: "
            f"{correct_count}/{question_count}",
            parse_mode="HTML",
            reply_markup=result_keyboard(
                school,
                user_id,
                attempt_id,
                str(_value(attempt, "mode", "full")),
                miniapp_url=settings.miniapp_url,
            ),
            disable_web_page_preview=True,
        )
        await _mark_viewed(attempt_id, user_id, settings)


def build_router(
    settings: Settings,
    school: SchoolConfig,
    catalog: DiagnosticCatalog,
) -> Router:
    router = Router(name="diagnostic")

    @router.message(CommandStart())
    @router.message(Command("diagnostics"))
    async def diagnostic_entry(message: Message) -> None:
        await send_home(message, settings, school, catalog)

    @router.message(Command("results"))
    async def results_command(message: Message) -> None:
        await send_results(message, settings, school, catalog)

    @router.message(Command("plan"))
    async def plan_command(message: Message) -> None:
        await send_plan(message, settings, school, catalog)

    @router.callback_query(F.data == "diag:menu")
    async def menu_callback(callback: CallbackQuery) -> None:
        await callback.answer()
        if callback.message:
            await callback.message.answer(
                await render_message("WELCOME", school),
                parse_mode="HTML",
                reply_markup=home_keyboard(school, settings.miniapp_url, callback.from_user.id),
                disable_web_page_preview=True,
            )

    @router.callback_query(F.data == "diag:results")
    async def results_callback(callback: CallbackQuery) -> None:
        await callback.answer()
        if callback.message:
            await _send_results_to(
                callback.message.answer,
                callback.from_user.id,
                settings,
                school,
                catalog,
            )

    @router.callback_query(F.data == "diag:plan")
    async def plan_callback(callback: CallbackQuery) -> None:
        await callback.answer()
        if callback.message:
            await _send_plan_to(
                callback.message.answer,
                callback.from_user.id,
                settings,
                school,
                catalog,
            )

    @router.callback_query(F.data.startswith("diag:result:"))
    async def result_callback(callback: CallbackQuery) -> None:
        await show_result(callback, settings, school, catalog)

    return router
