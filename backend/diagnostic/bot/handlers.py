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
from diagnostic.daily_plan import ensure_today_plan, plan_summary
from diagnostic.db import attempts, funnel
from diagnostic.messages import render_message
from diagnostic.school import SchoolConfig
from diagnostic.scoring import COVERAGE_LIMITATION, round_half_up
from diagnostic.settings import Settings

from .keyboards import home_keyboard, result_keyboard, results_keyboard, webapp_keyboard
from .sender import send_school_message


def _value(row: Mapping[str, Any], key: str, default: Any = None) -> Any:
    try:
        value = row[key]
    except (KeyError, TypeError):
        value = default
    return default if value is None else value


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
        await send_school_message(
            send_text=message.answer,
            send_photo=getattr(message, "answer_photo", None),
            school=school,
            message_key="DATA_ERASED",
            text=await render_message("DATA_ERASED", school),
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
    await send_school_message(
        send_text=message.answer,
        send_photo=getattr(message, "answer_photo", None),
        school=school,
        message_key="WELCOME",
        text=text,
        reply_markup=home_keyboard(school, settings.miniapp_url, user_id),
    )


async def send_results(
    message: Message,
    settings: Settings,
    school: SchoolConfig,
    catalog: DiagnosticCatalog,
) -> None:
    await _send_results_to(
        message,
        message.from_user.id,
        settings,
        school,
        catalog,
    )


async def _send_results_to(message, user_id: int, settings, school, catalog) -> None:
    rows = list(await attempts.list_completed_attempts(user_id))
    if not rows:
        text = await render_message("RESULTS_EMPTY", school)
        await send_school_message(
            send_text=message.answer,
            send_photo=getattr(message, "answer_photo", None),
            school=school,
            message_key="RESULTS_EMPTY",
            text=text,
            reply_markup=webapp_keyboard(school, settings.miniapp_url),
        )
        return

    interface = school.brand.interface
    fallback = interface.diagnostic_fallback
    lines = [f"<b>{html.escape(interface.results_heading, quote=True)}</b>", ""]
    for row in rows[:10]:
        subject = html.escape(_diagnostic_value(row, catalog, "subject", fallback), quote=True)
        correct = _value(row, "correct_count", 0)
        count = _value(row, "question_count", 0)
        accuracy = round_half_up(correct / count * 100) if count else 0
        mode = (
            interface.quick_result
            if _value(row, "mode", "quick") == "quick"
            else interface.full_result
        )
        mode = html.escape(mode, quote=True)
        lines.append(
            f"• <b>{subject}</b> · верно {correct}/{count} ({accuracy}%) · {mode}"
        )
    await send_school_message(
        send_text=message.answer,
        send_photo=getattr(message, "answer_photo", None),
        school=school,
        message_key="RESULTS",
        text="\n".join(lines),
        reply_markup=results_keyboard(
            school, rows[:10], settings.miniapp_url,
            timezone_name=settings.timezone,
        ),
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
        message,
        message.from_user.id,
        settings,
        school,
        catalog,
    )


def task_count_text(count: int) -> str:
    """Russian plural for the number of tasks in one day's plan."""
    tail = count % 100
    if 11 <= tail <= 14:
        return f"{count} заданий"
    last = count % 10
    if last == 1:
        return f"{count} задание"
    if 2 <= last <= 4:
        return f"{count} задания"
    return f"{count} заданий"


async def _send_plan_to(message, user_id: int, settings, school, catalog) -> None:
    interface = school.brand.interface
    try:
        plan = await ensure_today_plan(
            user_id=user_id,
            catalog=catalog,
            application_secret=settings.application_secret,
            timezone_name=settings.timezone,
        )
    except (RuntimeError, ValueError):
        plan = None
    summary = plan_summary(plan, catalog)
    if summary["status"] == "no_diagnostic":
        await send_school_message(
            send_text=message.answer,
            send_photo=getattr(message, "answer_photo", None),
            school=school,
            message_key="PLAN_EMPTY",
            text=await render_message("PLAN_EMPTY", school),
            reply_markup=webapp_keyboard(school, settings.miniapp_url),
        )
        return

    subject = html.escape(
        str(summary["subject"] or interface.diagnostic_fallback), quote=True
    )
    lines = [
        f"<b>{html.escape(interface.plan_for, quote=True)} {subject}</b>",
        "",
        f"Сегодня: {task_count_text(int(summary['total']))}, "
        f"выполнено {int(summary['completed'])}.",
    ]
    if summary["status"] == "done":
        lines.append(html.escape(interface.open_result_hint, quote=True))
    await send_school_message(
        send_text=message.answer,
        send_photo=getattr(message, "answer_photo", None),
        school=school,
        message_key="PLAN",
        text="\n".join(lines),
        reply_markup=webapp_keyboard(school, settings.miniapp_url, label=interface.plan),
    )


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
    question_count = html.escape(str(_value(attempt, "question_count", 0)), quote=True)
    correct_count = html.escape(str(_value(attempt, "correct_count", 0)), quote=True)
    if callback.message:
        await send_school_message(
            send_text=callback.message.answer,
            send_photo=getattr(callback.message, "answer_photo", None),
            school=school,
            message_key="RESULTS",
            text=f"<b>{subject}</b>\n"
            f"{html.escape(school.brand.pdf.correct_label, quote=True)}: "
            f"{correct_count}/{question_count}\n{COVERAGE_LIMITATION}",
            reply_markup=result_keyboard(
                school,
                user_id,
                attempt_id,
                str(_value(attempt, "mode", "full")),
                miniapp_url=settings.miniapp_url,
            ),
        )
        await _mark_viewed(attempt_id, user_id, settings)


def build_router(
    settings: Settings,
    school: SchoolConfig,
    catalog: DiagnosticCatalog,
) -> Router:
    router = Router(name="diagnostic")

    @router.message(Command("stop"))
    async def stop_notifications(message: Message) -> None:
        if message.from_user:
            await attempts.set_notification_preference(message.from_user.id, False)
            await message.answer(
                "Напоминания выключены.\n\n"
                "Результаты, план и сохранённый прогресс останутся на месте. "
                "Бот больше не будет писать о незавершённых диагностиках и "
                "следующих шагах.\n\n"
                "Чтобы снова получать напоминания, отправь /notifications."
            )

    @router.message(Command("notifications"))
    async def enable_notifications(message: Message) -> None:
        if message.from_user:
            await attempts.set_notification_preference(message.from_user.id, True)
            await message.answer(
                "Напоминания включены.\n\n"
                "Бот сообщит о готовом результате, незавершённой диагностике "
                "или полезном следующем шаге.\n\n"
                "Если захочешь снова отключить сообщения, отправь /stop."
            )

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
            await send_school_message(
                send_text=callback.message.answer,
                send_photo=getattr(callback.message, "answer_photo", None),
                school=school,
                message_key="WELCOME",
                text=await render_message("WELCOME", school),
                reply_markup=home_keyboard(school, settings.miniapp_url, callback.from_user.id),
            )

    @router.callback_query(F.data == "diag:results")
    async def results_callback(callback: CallbackQuery) -> None:
        await callback.answer()
        if callback.message:
            await _send_results_to(
                callback.message,
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
                callback.message,
                callback.from_user.id,
                settings,
                school,
                catalog,
            )

    @router.callback_query(F.data.startswith("diag:result:"))
    async def result_callback(callback: CallbackQuery) -> None:
        await show_result(callback, settings, school, catalog)

    return router
