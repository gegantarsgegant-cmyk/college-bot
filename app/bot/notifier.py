"""Cross-module helper to send notifications from web routes into the bot."""

from __future__ import annotations

import logging
from html import escape

from .. import models
from ..config import settings
from ..db import AsyncSessionLocal
from ..services import application_stats
from .bot import get_bot

log = logging.getLogger("college.bot.notifier")


PROGRAM_LABELS = {
    "music": "🎵 Музыка",
    "theology": "📖 Богословие",
    "theatre": "🎭 Театр",
}


def _format_application(app: models.Application, stats: dict[str, int] | None = None) -> str:
    """Beautiful HTML notification with emoji + structured layout."""
    program = PROGRAM_LABELS.get(app.program or "", escape(app.program or "—"))
    when = app.created_at.strftime("%d.%m.%Y · %H:%M")

    parts = [
        "🔔 <b>Новая заявка с сайта!</b>",
        "",
        "━━━━━━━━━━━━━━━━━━",
        f"👤 <b>{escape(app.name)} {escape(app.lastname)}</b>",
        f"🆔 Заявка <b>№{app.id}</b>",
        f"🕐 {when}",
        "━━━━━━━━━━━━━━━━━━",
    ]
    if app.phone:
        parts.append(f"📞 <b>Телефон:</b> <a href=\"tel:{escape(app.phone)}\">{escape(app.phone)}</a>")
    if app.program:
        parts.append(f"🎓 <b>Программа:</b> {program}")
    if app.church:
        parts.append(f"⛪ <b>Церковь:</b> {escape(app.church)}")
    if app.note:
        parts.append("")
        parts.append(f"💬 <i>{escape(app.note)}</i>")
    parts.append("")
    parts.append("👇 <i>Выберите действие:</i>")

    if stats:
        parts.append("")
        parts.append(
            f"📊 Всего новых: <b>{stats.get('new', 0)}</b> · "
            f"связались: <b>{stats.get('contacted', 0)}</b>"
        )

    return "\n".join(parts)


async def notify_new_application(app: models.Application) -> None:
    bot = get_bot()
    if bot is None:
        return

    from .handlers import application_kb

    async with AsyncSessionLocal() as session:
        stats = await application_stats(session)

    text = _format_application(app, stats)
    kb = application_kb(app.id)

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
            await bot.send_message(
                chat_id,
                text,
                reply_markup=kb,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("Failed to notify %s: %s", chat_id, exc)
        else:
            log.info("Notified admin %s about application #%s", chat_id, app.id)


def _notification_targets() -> list[int]:
    targets: list[int] = []
    if settings.TELEGRAM_NOTIFY_CHAT_ID:
        try:
            targets.append(int(settings.TELEGRAM_NOTIFY_CHAT_ID))
        except ValueError:
            pass
    targets.extend(settings.admin_ids)
    return list(dict.fromkeys(targets))


async def notify_stale_applications() -> int:
    """Find applications stuck in new/contacted for >=3 days, ping admins.

    Returns the number of reminders sent.
    """
    from datetime import datetime as _dt

    from ..services import stale_applications

    bot = get_bot()
    if bot is None:
        return 0
    targets = _notification_targets()
    if not targets:
        return 0

    sent = 0
    async with AsyncSessionLocal() as session:
        stale = await stale_applications(session, days=3)
        if not stale:
            return 0

        # Build a single digest message
        lines = ["⚠️ <b>Заявки без движения</b>", ""]
        ids: list[int] = []
        for a in stale[:30]:  # cap to keep telegram message sane
            age = (_dt.utcnow() - a.created_at).days
            program = PROGRAM_LABELS.get(a.program or "", escape(a.program or "—"))
            phone = f" · 📞 {escape(a.phone)}" if a.phone else ""
            lines.append(
                f"• №{a.id} <b>{escape(a.name)} {escape(a.lastname)}</b> · "
                f"{program} · висит <b>{age} дн.</b>{phone}"
            )
            ids.append(a.id)

        if len(stale) > 30:
            lines.append(f"\n…и ещё {len(stale) - 30} заявок")

        lines.append("")
        lines.append("👉 Откройте админку, чтобы связаться с абитуриентами.")

        text = "\n".join(lines)
        for chat_id in targets:
            try:
                await bot.send_message(chat_id, text, parse_mode="HTML", disable_web_page_preview=True)
                sent += 1
            except Exception as exc:  # noqa: BLE001
                log.warning("Failed to send stale digest to %s: %s", chat_id, exc)

        # Mark them so we don't ping again for at least 20 hours
        for a in stale:
            a.last_reminder_at = _dt.utcnow()
        await session.commit()

    return sent
