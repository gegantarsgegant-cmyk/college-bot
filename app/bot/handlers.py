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


def _admin_panel_url() -> str:
    """URL открываемый кнопкой Mini App."""
    return settings.PUBLIC_URL.rstrip("/") + "/admin/tg"


def _public_url() -> str:
    return settings.PUBLIC_URL.rstrip("/")


def _webapp_supported() -> bool:
    """Telegram WebApp требует HTTPS."""
    return settings.PUBLIC_URL.startswith("https://")


def _public_link_button_supported() -> bool:
    """Telegram отвергает URL-кнопки на localhost/127.0.0.1."""
    url = settings.PUBLIC_URL
    if not (url.startswith("http://") or url.startswith("https://")):
        return False
    bad_hosts = ("localhost", "127.0.0.1", "0.0.0.0")
    return not any(host in url for host in bad_hosts)


def admin_menu_kb(stats: dict[str, int] | None = None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if _webapp_supported():
        rows.append(
            [
                InlineKeyboardButton(
                    text="🛠 Открыть админ-панель",
                    web_app=WebAppInfo(url=_admin_panel_url()),
                )
            ]
        )
    elif _public_link_button_supported():
        rows.append(
            [
                InlineKeyboardButton(
                    text="🌐 Открыть админ-панель",
                    url=_admin_panel_url(),
                )
            ]
        )
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


def application_kb(app_id: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(text="⏳ В работу", callback_data=f"app:in_progress:{app_id}"),
            InlineKeyboardButton(text="✅ Принять", callback_data=f"app:accepted:{app_id}"),
        ],
        [
            InlineKeyboardButton(text="✖ Отклонить", callback_data=f"app:rejected:{app_id}"),
        ],
    ]
    if _webapp_supported():
        rows.append(
            [
                InlineKeyboardButton(
                    text="🛠 Открыть в админке",
                    web_app=WebAppInfo(
                        url=_admin_panel_url() + f"?app={app_id}#applications"
                    ),
                )
            ]
        )
    elif _public_link_button_supported():
        rows.append(
            [
                InlineKeyboardButton(
                    text="🌐 Открыть в админке",
                    url=_admin_panel_url() + f"?app={app_id}#applications",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


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
        f"⏳ В работе: <b>{stats.get('in_progress', 0)}</b>\n"
        f"✅ Принятые: <b>{stats.get('accepted', 0)}</b>\n"
        f"✖ Отклонённые: <b>{stats.get('rejected', 0)}</b>\n"
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
        reply_markup=admin_menu_kb(stats),
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
        await cb.message.answer(_format_stats(stats), reply_markup=admin_menu_kb(stats))
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
        "in_progress": ("⏳", "В работе"),
        "accepted": ("✅", "Принято"),
        "rejected": ("✖", "Отклонено"),
        "new": ("📥", "Новая"),
    }
    icon, label = label_map.get(status, ("•", status))
    if cb.message:
        try:
            new_text = (cb.message.html_text or cb.message.text or "")
            new_text += f"\n\n<i>{icon} Статус: <b>{escape(label)}</b></i>"
            await cb.message.edit_text(
                new_text, parse_mode="HTML", reply_markup=application_kb(app.id)
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
        reply_markup=admin_menu_kb(stats),
    )


# ============== Registration ==============

def register(dp: Dispatcher) -> None:
    dp.include_router(router)
