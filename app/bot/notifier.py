"""Cross-module helper to send notifications from web routes into the bot."""

from __future__ import annotations

import logging
from html import escape

from .. import models
from ..config import settings
from .bot import get_bot

log = logging.getLogger("college.bot.notifier")


def _format_application(app: models.Application) -> str:
    lines = [
        "<b>📥 Новая заявка</b>",
        f"<b>ID:</b> {app.id}",
        f"<b>Имя:</b> {escape(app.name)} {escape(app.lastname)}",
    ]
    if app.phone:
        lines.append(f"<b>Контакт:</b> {escape(app.phone)}")
    if app.program:
        lines.append(f"<b>Программа:</b> {escape(app.program)}")
    if app.church:
        lines.append(f"<b>Церковь:</b> {escape(app.church)}")
    if app.note:
        lines.append(f"<b>Сообщение:</b> {escape(app.note)}")
    return "\n".join(lines)


async def notify_new_application(app: models.Application) -> None:
    bot = get_bot()
    if bot is None:
        return
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    text = _format_application(app)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✓ В работу", callback_data=f"app:in_progress:{app.id}"),
                InlineKeyboardButton(text="✓ Принято", callback_data=f"app:accepted:{app.id}"),
                InlineKeyboardButton(text="✗ Отклонить", callback_data=f"app:rejected:{app.id}"),
            ]
        ]
    )

    targets: list[int] = []
    if settings.TELEGRAM_NOTIFY_CHAT_ID:
        try:
            targets.append(int(settings.TELEGRAM_NOTIFY_CHAT_ID))
        except ValueError:
            log.warning("Bad TELEGRAM_NOTIFY_CHAT_ID: %r", settings.TELEGRAM_NOTIFY_CHAT_ID)
    targets.extend(settings.admin_ids)

    if not targets:
        log.info("No notification targets for application #%s", app.id)
        return

    for chat_id in targets:
        try:
            await bot.send_message(chat_id, text, reply_markup=kb, parse_mode="HTML")
        except Exception as exc:  # noqa: BLE001
            log.warning("Failed to notify %s: %s", chat_id, exc)
        else:
            log.info("Notified admin %s about application #%s", chat_id, app.id)
