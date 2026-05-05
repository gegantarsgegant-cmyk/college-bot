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


def _format_application(
    app: models.Application,
    stats: dict[str, int] | None = None,
    *,
    inline_link_html: str = "",
) -> str:
    """HTML notification: header, blockquote with applicant info, optional comment quote, footer.

    `inline_link_html` is appended as a clickable link in the message body —
    used when a URL inline-keyboard button isn't usable (e.g. basic-auth tunnel).
    """
    program = PROGRAM_LABELS.get(app.program or "", escape(app.program or "—"))
    when = app.created_at.strftime("%d.%m.%Y · %H:%M")

    header = (
        f"🔔 <b>Новая заявка</b> · №{app.id} · <i>{when}</i>"
    )

    info_lines = [f"👤 <b>{escape(app.name)} {escape(app.lastname)}</b>"]
    if app.phone:
        info_lines.append(
            f"📞 <a href=\"tel:{escape(app.phone)}\">{escape(app.phone)}</a>"
        )
    if app.program:
        info_lines.append(f"🎓 {program}")
    if app.church:
        info_lines.append(f"⛪ {escape(app.church)}")
    info_block = "<blockquote>" + "\n".join(info_lines) + "</blockquote>"

    parts = [header, "", info_block]

    if app.note:
        comment = escape(app.note).strip()
        parts.append("")
        parts.append(f"<blockquote>💬 {comment}</blockquote>")

    if stats:
        parts.append("")
        parts.append(
            f"📊 Всего новых: <b>{stats.get('new', 0)}</b> · "
            f"связались: <b>{stats.get('contacted', 0)}</b>"
        )

    if inline_link_html:
        parts.append("")
        parts.append(f"👉 {inline_link_html}")

    return "\n".join(parts)


async def notify_new_application(app: models.Application) -> None:
    bot = get_bot()
    if bot is None:
        return

    from .handlers import admin_link_html, application_kb

    async with AsyncSessionLocal() as session:
        stats = await application_stats(session)

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
        link_html = admin_link_html(
            chat_id,
            text="🛠 Открыть заявку в админке",
            next_path=f"/admin/applications?app={app.id}",
        )
        text = _format_application(app, stats, inline_link_html=link_html)
        try:
            await bot.send_message(
                chat_id,
                text,
                reply_markup=application_kb(app.id, tg_user_id=chat_id),
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


def _format_stale_app(a: models.Application, age_days: int) -> str:
    """One application as a blockquote — used in stale digest."""
    program = PROGRAM_LABELS.get(a.program or "", escape(a.program or "—"))
    lines = [
        f"👤 <b>{escape(a.name)} {escape(a.lastname)}</b> · №{a.id}",
        f"🎓 {program}",
    ]
    if a.phone:
        lines.append(f"📞 <a href=\"tel:{escape(a.phone)}\">{escape(a.phone)}</a>")
    lines.append(f"🕐 Висит <b>{age_days} дн.</b>")
    return "<blockquote>" + "\n".join(lines) + "</blockquote>"


async def notify_stale_applications() -> int:
    """Find applications stuck in new/contacted for >=3 days, ping admins.

    Returns the number of reminders sent.
    """
    from datetime import datetime as _dt

    from ..services import stale_applications
    from .handlers import admin_link_html, admin_link_kb

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

        header = (
            f"⚠️ <b>Заявки без движения</b> · <i>{len(stale)} шт.</i>"
        )
        blocks: list[str] = [header]
        for a in stale[:30]:
            age = (_dt.utcnow() - a.created_at).days
            blocks.append("")  # blank line between entries
            blocks.append(_format_stale_app(a, age))

        if len(stale) > 30:
            blocks.append("")
            blocks.append(f"…и ещё <b>{len(stale) - 30}</b> заявок.")

        for chat_id in targets:
            link_html = admin_link_html(
                chat_id,
                text="🛠 Открыть в админке",
                next_path="/admin/applications",
            )
            chat_blocks = list(blocks)
            if link_html:
                chat_blocks.append("")
                chat_blocks.append(f"👉 {link_html}")
            text = "\n".join(chat_blocks)
            try:
                await bot.send_message(
                    chat_id,
                    text,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                    reply_markup=admin_link_kb(tg_user_id=chat_id),
                )
                sent += 1
            except Exception as exc:  # noqa: BLE001
                log.warning("Failed to send stale digest to %s: %s", chat_id, exc)

        # Mark them so we don't ping again for at least 20 hours
        for a in stale:
            a.last_reminder_at = _dt.utcnow()
        await session.commit()

    return sent
