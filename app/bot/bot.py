"""aiogram bot factory and lifecycle."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from ..config import settings

log = logging.getLogger("college.bot")

_bot: Bot | None = None
_dp: Dispatcher | None = None
_polling_task: asyncio.Task | None = None


def get_bot() -> Bot | None:
    return _bot


def get_dp() -> Dispatcher | None:
    return _dp


def build_bot() -> tuple[Bot | None, Dispatcher | None]:
    """Construct the Bot/Dispatcher singletons. Safe no-op if no token configured."""
    global _bot, _dp
    if _bot is not None:
        return _bot, _dp
    if not settings.bot_enabled:
        log.warning("TELEGRAM_BOT_TOKEN not set; bot disabled.")
        return None, None
    _bot = Bot(
        token=settings.TELEGRAM_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    _dp = Dispatcher(storage=MemoryStorage())

    # Register handlers (import here to avoid circulars).
    from . import handlers  # noqa: F401
    handlers.register(_dp)

    return _bot, _dp


async def start_bot() -> None:
    """Kick off polling in the background. Idempotent."""
    global _polling_task
    bot, dp = build_bot()
    if bot is None or dp is None:
        return
    if _polling_task and not _polling_task.done():
        return
    log.info("Starting Telegram bot in %s mode", settings.BOT_MODE)
    if settings.BOT_MODE == "polling":
        await bot.delete_webhook(drop_pending_updates=False)
        loop = asyncio.get_event_loop()
        _polling_task = loop.create_task(dp.start_polling(bot, handle_signals=False))
    elif settings.BOT_MODE == "webhook":
        if not settings.WEBHOOK_BASE_URL:
            log.error("BOT_MODE=webhook but WEBHOOK_BASE_URL is empty")
            return
        url = settings.WEBHOOK_BASE_URL.rstrip("/") + "/bot/webhook"
        await bot.set_webhook(
            url=url,
            secret_token=settings.WEBHOOK_SECRET or None,
            drop_pending_updates=False,
        )
        log.info("Webhook set to %s", url)


async def stop_bot() -> None:
    global _polling_task
    if _polling_task and not _polling_task.done():
        _polling_task.cancel()
        try:
            await _polling_task
        except (asyncio.CancelledError, Exception):
            pass
    _polling_task = None


async def shutdown_bot() -> None:
    await stop_bot()
    if _bot is not None:
        try:
            await _bot.session.close()
        except Exception:  # noqa: BLE001
            pass


def run_polling() -> None:
    """Standalone runner if you want to run only the bot (no web)."""
    asyncio.run(_run())


async def _run() -> None:
    bot, dp = build_bot()
    if bot is None or dp is None:
        raise SystemExit("TELEGRAM_BOT_TOKEN not set")
    await bot.delete_webhook(drop_pending_updates=False)
    await dp.start_polling(bot)
