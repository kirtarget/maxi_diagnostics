"""Polling entrypoint for the standalone diagnostic Telegram bot."""

from __future__ import annotations

import asyncio
import logging
import signal
from collections.abc import Awaitable

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand

from diagnostic.catalog import load_catalog
from diagnostic.db.core import close_db, init_db
from diagnostic.db.attempts import store_report_asset_bundle
from diagnostic.api.sessions import prepare_report_assets
from diagnostic.school import SchoolConfig, load_school
from diagnostic.settings import Settings
from diagnostic.worker import build_worker_scheduler

from .handlers import build_router


logger = logging.getLogger(__name__)
CONFIGURE_TIMEOUT_SECONDS = 5


def build_bot_commands(school: SchoolConfig) -> list[BotCommand]:
    labels = school.brand.interface
    return [
        BotCommand(command="start", description=labels.command_start),
        BotCommand(command="diagnostics", description=labels.command_diagnostics),
        BotCommand(command="results", description=labels.command_results),
        BotCommand(command="plan", description=labels.command_plan),
    ]


async def _run_configuration(operation: Awaitable[object], name: str) -> None:
    try:
        await asyncio.wait_for(operation, timeout=CONFIGURE_TIMEOUT_SECONDS)
    except Exception:
        logger.warning("telegram_%s_failed", name, exc_info=True)


async def configure_bot_safely(bot: Bot, school: SchoolConfig) -> None:
    await _run_configuration(bot.set_my_commands(build_bot_commands(school)), "set_commands")
    try:
        await asyncio.wait_for(
            bot.delete_webhook(drop_pending_updates=False),
            timeout=CONFIGURE_TIMEOUT_SECONDS,
        )
    except Exception:
        logger.warning("telegram_delete_webhook_failed")
        raise RuntimeError("telegram_delete_webhook_failed") from None


async def wait_for_worker_shutdown() -> None:
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    registered = False
    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signum, stopped.set)
            registered = True
        except NotImplementedError:
            continue
    if registered:
        await stopped.wait()
    else:
        await asyncio.Future()


async def main() -> None:
    settings = Settings.from_env(require_admin=False)
    school = load_school()
    catalog = load_catalog(school)
    bot: Bot | None = None
    scheduler = None

    try:
        await init_db(settings.database_url, school)
        bundle_id, bundle = prepare_report_assets(school, catalog)
        await store_report_asset_bundle(bundle_id, bundle)
        bot = Bot(token=settings.bot_token)
        dispatcher = None
        if settings.bot_polling_enabled:
            dispatcher = Dispatcher()
            dispatcher.include_router(build_router(settings, school, catalog))
        scheduler = build_worker_scheduler(bot, settings, school, catalog)
        scheduler.start()
        if dispatcher is None:
            await wait_for_worker_shutdown()
        else:
            await configure_bot_safely(bot, school)
            await dispatcher.start_polling(
                bot,
                allowed_updates=dispatcher.resolve_used_update_types(),
            )
    finally:
        try:
            try:
                if scheduler is not None and scheduler.running:
                    scheduler.shutdown(wait=False)
            finally:
                if bot is not None:
                    await bot.session.close()
        finally:
            await close_db()


if __name__ == "__main__":
    asyncio.run(main())
