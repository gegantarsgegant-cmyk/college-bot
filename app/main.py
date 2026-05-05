from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from .bot import shutdown_bot, start_bot
from .config import STATIC_DIR, settings
from .db import AsyncSessionLocal, init_db
from .routers import admin as admin_router
from .routers import api as api_router
from .routers import site as site_router
from .services import (
    ensure_admin_user,
    ensure_default_programs,
    ensure_default_settings,
    ensure_default_teachers,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("college")


async def _stale_reminders_loop() -> None:
    """Background task: every 12h check for stale applications and ping admins.

    Cancellable via task.cancel() during shutdown.
    """
    from .bot.notifier import notify_stale_applications

    # Wait a bit so the bot has time to start before the first check.
    await asyncio.sleep(60)
    while True:
        try:
            n = await notify_stale_applications()
            if n:
                log.info("Stale applications digest sent to %s admin chat(s)", n)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.warning("Stale-reminders task failed: %s", exc)
        # Run twice a day. The notifier itself rate-limits per-application.
        await asyncio.sleep(12 * 3600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    async with AsyncSessionLocal() as session:
        await ensure_admin_user(session, settings.ADMIN_USERNAME, settings.ADMIN_PASSWORD)
        await ensure_default_settings(session)
        await ensure_default_teachers(session)
        await ensure_default_programs(session)
    if settings.bot_enabled:
        await start_bot()
    else:
        log.warning("Bot disabled (no TELEGRAM_BOT_TOKEN). Web only.")
    reminder_task = asyncio.create_task(_stale_reminders_loop())
    try:
        yield
    finally:
        reminder_task.cancel()
        try:
            await reminder_task
        except (asyncio.CancelledError, Exception):
            pass
        await shutdown_bot()


app = FastAPI(title="Bible College ХВЕ", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.include_router(site_router.router)
app.include_router(api_router.router)
app.include_router(admin_router.router)


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    fav = STATIC_DIR / "favicon" / "favicon.ico"
    if fav.is_file():
        return RedirectResponse("/static/favicon/favicon.ico")
    return Response(status_code=204)


@app.post("/bot/webhook")
async def bot_webhook(request: Request):
    """Webhook endpoint when BOT_MODE=webhook."""
    if settings.BOT_MODE != "webhook":
        raise HTTPException(404)
    if settings.WEBHOOK_SECRET:
        provided = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if provided != settings.WEBHOOK_SECRET:
            raise HTTPException(403)

    from aiogram.types import Update

    from .bot.bot import build_bot

    bot, dp = build_bot()
    if bot is None or dp is None:
        raise HTTPException(503, "Bot not configured")
    payload = await request.json()
    update = Update.model_validate(payload)
    await dp.feed_update(bot, update)
    return {"ok": True}


def _ensure_user_assets() -> None:
    """If user dropped fonts/ and favicon/ next to college.html, copy to static."""
    project_static = STATIC_DIR
    fonts_dir = project_static / "fonts"
    favicon_dir = project_static / "favicon"
    fonts_dir.mkdir(parents=True, exist_ok=True)
    favicon_dir.mkdir(parents=True, exist_ok=True)


_ensure_user_assets()


def main() -> None:
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
