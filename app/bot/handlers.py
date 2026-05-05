"""Telegram bot — admin-only.

Бот предназначен исключительно для администрации колледжа.
Минимальный набор функций:
  - `/start` показывает админ-меню с кнопкой WebApp на админ-панель
    и сводкой статистики по заявкам.
  - При создании заявки на сайте бот шлёт админам красиво
    отформатированное HTML-уведомление с эмодзи, статус-кнопками
    и кнопкой WebApp «Открыть в админке» (см. `notifier.py`).
  - Колбэки `app:<status>:<id>` обрабатывают смену статуса заявки
    прямо из чата.

Никаких CRUD/FSM команд — всё управление через админ-панель.
"""

from __future__ import annotations

import logging
from html import escape

from aiogram import Dispatcher, F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardRemove,
    WebAppInfo,
)

from .. import models
from ..config import settings
from ..db import AsyncSessionLocal
from ..services import application_stats, update_application_status

log = logging.getLogger("college.bot.handlers")
router = Router(name="college")


# ============== Helpers ==============

def is_admin(user_id: int) -> bool:
    return user_id in settings.admin_ids


def _bot_base_url(*, with_creds: bool = True) -> str:
    """Base URL used for links sent to Telegram.

    If `with_creds` is True (default) and BOT_PUBLIC_URL is configured with
    embedded basic-auth credentials, those credentials are kept in the URL —
    used for inline `<a>` links that Telegram opens in the system browser
    (which honours `user:pass@` in the URL).

    If `with_creds` is False, any embedded userinfo is stripped — used for
    inline-keyboard URL buttons because Telegram rejects URLs with userinfo
    via `BUTTON_URL_INVALID`.
    """
    base = (settings.BOT_PUBLIC_URL or settings.PUBLIC_URL).rstrip("/")
    if with_creds:
        return base
    if "://" in base:
        scheme, rest = base.split("://", 1)
        if "@" in rest.split("/", 1)[0]:
            host_and_path = rest.split("@", 1)[1]
            return f"{scheme}://{host_and_path}"
    return base


def _admin_panel_url() -> str:
    """URL открываемый кнопкой Mini App (Telegram WebApp)."""
    # WebApp also forbids userinfo in URL — keep it clean.
    return _bot_base_url(with_creds=False) + "/admin/tg"


def _admin_magic_url(
    tg_user_id: int,
    *,
    next_path: str = "/admin/",
    with_creds: bool = True,
) -> str:
    """One-shot login URL for the given Telegram admin."""
    from urllib.parse import quote

    from ..auth import make_magic_token

    token = make_magic_token(tg_user_id)
    base = _bot_base_url(with_creds=with_creds)
    return f"{base}/admin/magic?t={token}&next={quote(next_path)}"


def _public_url() -> str:
    """User-facing site URL (never contains basic-auth creds)."""
    return settings.PUBLIC_URL.rstrip("/")


def _webapp_supported() -> bool:
    """Telegram WebApp требует HTTPS."""
    base = _bot_base_url(with_creds=False)
    return base.startswith("https://")


def _public_link_button_supported() -> bool:
    """Telegram отвергает URL-кнопки на localhost/127.0.0.1."""
    url = _bot_base_url(with_creds=False)
    if not (url.startswith("http://") or url.startswith("https://")):
        return False
    host_part = url.split("://", 1)[1].split("/", 1)[0]
    bad_hosts = ("localhost", "127.0.0.1", "0.0.0.0")
    return not any(host_part.startswith(h) for h in bad_hosts)


def _has_embedded_creds() -> bool:
    """True if BOT_PUBLIC_URL has user:pass@ — implies tunnel basic auth."""
    base = (settings.BOT_PUBLIC_URL or "").strip()
    if "://" not in base:
        return False
    rest = base.split("://", 1)[1]
    return "@" in rest.split("/", 1)[0]


def _open_admin_button(
    tg_user_id: int | None,
    *,
    text: str = "🛠 Открыть админ-панель",
    next_path: str = "/admin/",
) -> InlineKeyboardButton | None:
    """Build a button that opens the admin panel.

    URLs sent in inline-button MUST NOT contain userinfo (`user:pass@`) — the
    Telegram Bot API rejects them with `BUTTON_URL_INVALID`. So when the
    public host is behind a basic-auth tunnel (`_has_embedded_creds()`), the
    button is omitted; in its place the caller renders an inline `<a>` link
    in the message body which Telegram opens in the system browser (and the
    system browser respects `user:pass@`).
    """
    if _has_embedded_creds():
        return None
    if tg_user_id is not None and is_admin(tg_user_id) and _public_link_button_supported():
        url = _admin_magic_url(tg_user_id, next_path=next_path, with_creds=False)
        return InlineKeyboardButton(text=text, url=url)
    if _webapp_supported():
        return InlineKeyboardButton(
            text=text, web_app=WebAppInfo(url=_admin_panel_url())
        )
    if _public_link_button_supported():
        return InlineKeyboardButton(text=text, url=_admin_panel_url())
    return None


def admin_link_html(
    tg_user_id: int | None,
    *,
    text: str = "🛠 Открыть в админке",
    next_path: str = "/admin/",
) -> str:
    """Inline `<a>` link rendered in message body — used as a fallback when
    a URL inline-keyboard button is not possible (basic-auth tunnel).
    Returns an empty string if we have no usable URL.
    """
    if tg_user_id is None or not is_admin(tg_user_id):
        return ""
    url = _admin_magic_url(tg_user_id, next_path=next_path, with_creds=True)
    return f"<a href=\"{escape(url, quote=True)}\">{escape(text)}</a>"


def admin_menu_kb(
    stats: dict[str, int] | None = None,
    tg_user_id: int | None = None,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    btn = _open_admin_button(tg_user_id)
    if btn:
        rows.append([btn])
    new_count = (stats or {}).get("new", 0)
    rows.append(
        [
            InlineKeyboardButton(
                text=f"📥 Новые заявки{(' · ' + str(new_count)) if new_count else ''}",
                callback_data="adm:stats",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def application_kb(app_id: int, tg_user_id: int | None = None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(text="📞 Связались", callback_data=f"app:contacted:{app_id}"),
            InlineKeyboardButton(text="📄 Документы", callback_data=f"app:docs_submitted:{app_id}"),
        ],
        [
            InlineKeyboardButton(text="✅ Зачислить", callback_data=f"app:accepted:{app_id}"),
            InlineKeyboardButton(text="✖ Отказ", callback_data=f"app:rejected:{app_id}"),
        ],
    ]
    btn = _open_admin_button(
        tg_user_id,
        text="🛠 Посмотреть в админке",
        next_path=f"/admin/applications?app={app_id}",
    )
    if btn:
        rows.append([btn])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_link_kb(tg_user_id: int | None = None) -> InlineKeyboardMarkup | None:
    """Single-button keyboard that opens the admin panel (for stale digest etc.)."""
    btn = _open_admin_button(
        tg_user_id,
        text="🛠 Открыть в админке",
        next_path="/admin/applications",
    )
    if btn is None:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[btn]])


async def _ensure_bot_user(message: Message) -> None:
    if not message.from_user:
        return
    async with AsyncSessionLocal() as session:
        u = await session.get(models.BotUser, message.from_user.id)
        if u is None:
            session.add(
                models.BotUser(
                    id=message.from_user.id,
                    username=message.from_user.username or "",
                    first_name=message.from_user.first_name or "",
                    last_name=message.from_user.last_name or "",
                    is_admin=is_admin(message.from_user.id),
                )
            )
        else:
            u.username = message.from_user.username or ""
            u.first_name = message.from_user.first_name or ""
            u.last_name = message.from_user.last_name or ""
            u.is_admin = is_admin(message.from_user.id)
        await session.commit()


def _format_stats(stats: dict[str, int]) -> str:
    return (
        "📊 <b>Статистика заявок</b>\n\n"
        f"📥 Новые: <b>{stats.get('new', 0)}</b>\n"
        f"📞 Связались: <b>{stats.get('contacted', 0)}</b>\n"
        f"📄 Документы: <b>{stats.get('docs_submitted', 0)}</b>\n"
        f"✅ Зачислены: <b>{stats.get('accepted', 0)}</b>\n"
        f"✖ Отказы: <b>{stats.get('rejected', 0)}</b>\n"
        f"━━━━━━━━━━━━━\n"
        f"📊 Всего: <b>{stats.get('total', 0)}</b>"
    )


# ============== /start ==============

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await _ensure_bot_user(message)
    user = message.from_user
    name = (user.first_name if user else "") or "друг"

    if not user or not is_admin(user.id):
        # Пользователю бот не нужен — отправляем на сайт.
        await message.answer(
            f"Здравствуйте, {escape(name)}! 👋\n\n"
            "Этот бот предназначен только для администрации "
            "<b>Библейского колледжа ХВЕ</b>.\n\n"
            "Чтобы узнать о колледже, посмотреть программы или "
            f"оставить заявку — пожалуйста, перейдите на сайт:\n{_public_url()}",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    async with AsyncSessionLocal() as session:
        stats = await application_stats(session)

    await message.answer(
        f"👋 Добрый день, <b>{escape(name)}</b>!\n\n"
        "Это <b>административный бот</b> Библейского колледжа ХВЕ.\n"
        "Сюда приходят уведомления о заявках с сайта.\n\n"
        + _format_stats(stats),
        reply_markup=admin_menu_kb(stats, tg_user_id=user.id),
    )


# ============== Callbacks ==============

@router.callback_query(F.data == "adm:stats")
async def cb_stats(cb: CallbackQuery):
    if not cb.from_user or not is_admin(cb.from_user.id):
        await cb.answer("⛔ Только админы", show_alert=True)
        return
    async with AsyncSessionLocal() as session:
        stats = await application_stats(session)
    if cb.message:
        await cb.message.answer(
            _format_stats(stats),
            reply_markup=admin_menu_kb(stats, tg_user_id=cb.from_user.id),
        )
    await cb.answer()


# ============== Application status callbacks ==============

@router.callback_query(F.data.startswith("app:"))
async def application_action(cb: CallbackQuery):
    if not cb.from_user or not is_admin(cb.from_user.id):
        await cb.answer("⛔ Только админы", show_alert=True)
        return
    parts = (cb.data or "").split(":")
    if len(parts) != 3:
        await cb.answer()
        return
    _, status, sid = parts
    try:
        app_id = int(sid)
    except ValueError:
        await cb.answer()
        return
    async with AsyncSessionLocal() as session:
        app = await update_application_status(session, app_id, status)
    if app is None:
        await cb.answer("Не найдено", show_alert=True)
        return
    label_map = {
        "contacted": ("📞", "Связались"),
        "docs_submitted": ("📄", "Документы поданы"),
        "accepted": ("✅", "Зачислен"),
        "rejected": ("✖", "Отказ"),
        "new": ("📥", "Новая"),
    }
    icon, label = label_map.get(status, ("•", status))
    if cb.message:
        try:
            new_text = (cb.message.html_text or cb.message.text or "")
            new_text += f"\n\n<i>{icon} Статус: <b>{escape(label)}</b></i>"
            await cb.message.edit_text(
                new_text,
                parse_mode="HTML",
                reply_markup=application_kb(app.id, tg_user_id=cb.from_user.id),
            )
        except Exception:  # noqa: BLE001
            pass
    await cb.answer(f"{icon} Заявка #{app.id}: {label}")


# ============== Fallback ==============

@router.message()
async def fallback(message: Message):
    user = message.from_user
    if not user or not is_admin(user.id):
        await message.answer(
            "Этот бот только для администрации.\n"
            f"Сайт колледжа: {_public_url()}"
        )
        return
    # Для админов — просто показываем меню.
    async with AsyncSessionLocal() as session:
        stats = await application_stats(session)
    await message.answer(
        "Используйте кнопки ниже:\n\n" + _format_stats(stats),
        reply_markup=admin_menu_kb(stats, tg_user_id=user.id),
    )


# ============== Registration ==============

def register(dp: Dispatcher) -> None:
    dp.include_router(router)
