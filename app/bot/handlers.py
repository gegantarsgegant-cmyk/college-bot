"""Telegram bot — admin-only.

Регулярные пользователи общаются только с сайтом. Бот предназначен
исключительно для администрации:
  - получает уведомления о новых заявках с inline-кнопками управления;
  - открывает админ-панель в виде Telegram Mini App;
  - даёт быстрые FSM-команды на создание новостей/событий/преподавателей/документов
    прямо из чата (для удобства с телефона).
"""

from __future__ import annotations

import logging
from html import escape
from pathlib import Path
from typing import cast

from aiogram import Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    WebAppInfo,
)

from .. import models
from ..config import settings
from ..db import AsyncSessionLocal
from ..services import (
    list_applications,
    update_application_status,
)
from .states import DocumentCreate, EventCreate, NewsCreate, TeacherCreate

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
    """Telegram WebApp требует HTTPS (кроме t.me/test). Проверяем что URL https://."""
    return settings.PUBLIC_URL.startswith("https://")


def _public_link_button_supported() -> bool:
    """Telegram отвергает URL-кнопки на localhost/127.0.0.1.

    Возвращает True только если PUBLIC_URL — реальный публичный URL,
    с которым Telegram позволит привязать inline url-кнопку.
    """
    url = settings.PUBLIC_URL
    if not (url.startswith("http://") or url.startswith("https://")):
        return False
    bad_hosts = ("localhost", "127.0.0.1", "0.0.0.0")
    return not any(host in url for host in bad_hosts)


def admin_menu_kb() -> InlineKeyboardMarkup:
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
    rows.append([InlineKeyboardButton(text="📥 Заявки", callback_data="adm:apps")])
    rows.append(
        [
            InlineKeyboardButton(text="📰 Новость", callback_data="adm:news"),
            InlineKeyboardButton(text="📅 Событие", callback_data="adm:events"),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(text="👥 Преподаватель", callback_data="adm:teachers"),
            InlineKeyboardButton(text="📄 Документ", callback_data="adm:docs"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def application_kb(app_id: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(text="✓ В работу", callback_data=f"app:in_progress:{app_id}"),
            InlineKeyboardButton(text="✓ Принято", callback_data=f"app:accepted:{app_id}"),
            InlineKeyboardButton(text="✗ Отклонить", callback_data=f"app:rejected:{app_id}"),
        ]
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
    return rows_to_markup(rows)


def rows_to_markup(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _ensure_bot_user(message: Message) -> None:
    if not message.from_user:
        return
    async with AsyncSessionLocal() as session:
        u = await session.get(models.BotUser, message.from_user.id)
        from datetime import datetime as _dt

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
            u.last_seen = _dt.utcnow()
        await session.commit()


async def _safe_answer(event: Message | CallbackQuery, text: str, **kw):
    if isinstance(event, CallbackQuery):
        if event.message:
            await event.message.answer(text, **kw)
        await event.answer()
    else:
        await event.answer(text, **kw)


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
            f"Здравствуйте, {escape(name)}!\n\n"
            "Этот бот предназначен только для администрации Библейского колледжа ХВЕ.\n\n"
            f"Чтобы узнать больше о колледже, посмотреть программы или оставить заявку — пожалуйста, перейдите на сайт:\n{_public_url()}",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    await message.answer(
        f"Добрый день, {escape(name)}! 👋\n\n"
        "Это <b>административный бот</b> Библейского колледжа ХВЕ.\n"
        "Сюда приходят заявки с сайта, отсюда вы управляете содержимым.\n\n"
        "Используйте кнопки ниже или команды:\n"
        "/admin — это меню\n"
        "/applications — последние новые заявки\n"
        "/newpost — добавить новость\n"
        "/newevent — добавить событие\n"
        "/newteacher — добавить преподавателя\n"
        "/newdoc — загрузить документ\n"
        "/cancel — отменить текущую операцию",
        reply_markup=admin_menu_kb(),
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    if not message.from_user or not is_admin(message.from_user.id):
        await message.answer(
            "Этот бот только для администрации. Сайт колледжа: " + _public_url()
        )
        return
    await message.answer(
        "<b>Команды бота</b>\n"
        "/admin — главное меню (с кнопкой админ-панели)\n"
        "/applications — список новых заявок\n"
        "/newpost — добавить новость\n"
        "/newevent — добавить событие\n"
        "/newteacher — добавить преподавателя\n"
        "/newdoc — загрузить документ\n"
        "/cancel — отменить текущую операцию"
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.", reply_markup=ReplyKeyboardRemove())


# ============== /admin ==============

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    user = message.from_user
    if not user or not is_admin(user.id):
        await message.answer("⛔ Доступ только для администраторов.")
        return
    await message.answer(
        "⚙ <b>Админ-меню</b>\n\nОткройте админ-панель кнопкой ниже или используйте быстрые команды.",
        reply_markup=admin_menu_kb(),
    )


@router.callback_query(F.data == "adm:apps")
@router.message(Command("applications"))
async def list_apps(event: Message | CallbackQuery):
    user = event.from_user
    if not user or not is_admin(user.id):
        await _safe_answer(event, "⛔ Доступ только для администраторов.")
        return
    async with AsyncSessionLocal() as session:
        apps = await list_applications(session, status="new", limit=10)
    target = event.message if isinstance(event, CallbackQuery) else event
    if not apps:
        await _safe_answer(event, "Новых заявок нет 🎉")
        return
    if target:
        await target.answer(f"<b>Новых заявок: {len(apps)}</b>")
        for app in apps:
            await target.answer(_format_application(app), reply_markup=application_kb(app.id))
    if isinstance(event, CallbackQuery):
        await event.answer()


def _format_application(app: models.Application) -> str:
    lines = [
        f"<b>📥 Заявка #{app.id}</b>",
        f"<b>{escape(app.name)} {escape(app.lastname)}</b>",
    ]
    if app.phone:
        lines.append(f"📞 {escape(app.phone)}")
    if app.program:
        lines.append(f"🎓 {escape(app.program)}")
    if app.church:
        lines.append(f"⛪ {escape(app.church)}")
    if app.note:
        lines.append(f"💬 {escape(app.note)}")
    return "\n".join(lines)


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
        "in_progress": "В работе",
        "accepted": "Принято",
        "rejected": "Отклонено",
        "new": "Новая",
    }
    label = label_map.get(status, status)
    if cb.message:
        try:
            # Заменяем inline-клавиатуру на отметку статуса.
            new_text = (cb.message.html_text or cb.message.text or "")
            new_text += f"\n\n<i>Статус: <b>{escape(label)}</b></i>"
            await cb.message.edit_text(new_text, parse_mode="HTML")
        except Exception:  # noqa: BLE001
            pass
    await cb.answer(f"Заявка #{app.id}: {label}")


# ============== News creation (FSM) ==============

@router.callback_query(F.data == "adm:news")
@router.message(Command("newpost"))
async def news_start(event: Message | CallbackQuery, state: FSMContext):
    user = event.from_user
    if not user or not is_admin(user.id):
        await _safe_answer(event, "⛔")
        return
    await state.set_state(NewsCreate.title)
    await _safe_answer(event, "Введите <b>заголовок</b> новости:")


@router.message(NewsCreate.title)
async def news_title(message: Message, state: FSMContext):
    await state.update_data(title=(message.text or "").strip()[:255])
    await state.set_state(NewsCreate.body)
    await message.answer("Текст новости:")


@router.message(NewsCreate.body)
async def news_body(message: Message, state: FSMContext):
    await state.update_data(body=(message.text or "").strip())
    await state.set_state(NewsCreate.photo)
    await message.answer("Прикрепите фото (или отправьте /skip).")


@router.message(NewsCreate.photo, Command("skip"))
async def news_photo_skip(message: Message, state: FSMContext):
    await _save_news(message, state, image_url=None)


@router.message(NewsCreate.photo, F.photo)
async def news_photo(message: Message, state: FSMContext):
    image_url = await _download_telegram_photo(message)
    await _save_news(message, state, image_url=image_url)


async def _save_news(message: Message, state: FSMContext, image_url: str | None):
    data = await state.get_data()
    async with AsyncSessionLocal() as session:
        obj = models.News(
            title=data.get("title", "Без названия"),
            body=data.get("body", ""),
            image_url=image_url,
            published=True,
        )
        session.add(obj)
        await session.commit()
    await state.clear()
    await message.answer("✅ Новость опубликована.")


# ============== Event creation (FSM) ==============

@router.callback_query(F.data == "adm:events")
@router.message(Command("newevent"))
async def event_start(event: Message | CallbackQuery, state: FSMContext):
    user = event.from_user
    if not user or not is_admin(user.id):
        await _safe_answer(event, "⛔")
        return
    await state.set_state(EventCreate.title)
    await _safe_answer(event, "Название события:")


@router.message(EventCreate.title)
async def event_title(message: Message, state: FSMContext):
    await state.update_data(title=(message.text or "").strip()[:255])
    await state.set_state(EventCreate.starts_at)
    await message.answer("Дата и время? Формат: <code>ДД.ММ.ГГГГ ЧЧ:ММ</code>")


@router.message(EventCreate.starts_at)
async def event_starts_at(message: Message, state: FSMContext):
    from datetime import datetime as _dt

    raw = (message.text or "").strip()
    try:
        dt = _dt.strptime(raw, "%d.%m.%Y %H:%M")
    except ValueError:
        await message.answer("Не понял дату. Попробуйте ещё раз: <code>ДД.ММ.ГГГГ ЧЧ:ММ</code>")
        return
    await state.update_data(starts_at=dt.isoformat())
    await state.set_state(EventCreate.location)
    await message.answer("Место проведения (или /skip):")


@router.message(EventCreate.location, Command("skip"))
async def event_location_skip(message: Message, state: FSMContext):
    await _save_event(message, state, location="")


@router.message(EventCreate.location)
async def event_location(message: Message, state: FSMContext):
    await _save_event(message, state, location=(message.text or "").strip()[:255])


async def _save_event(message: Message, state: FSMContext, location: str):
    from datetime import datetime as _dt

    data = await state.get_data()
    async with AsyncSessionLocal() as session:
        obj = models.Event(
            title=data.get("title", ""),
            starts_at=_dt.fromisoformat(data["starts_at"]),
            location=location,
            published=True,
        )
        session.add(obj)
        await session.commit()
    await state.clear()
    await message.answer("✅ Событие добавлено.")


# ============== Teacher creation (FSM) ==============

@router.callback_query(F.data == "adm:teachers")
@router.message(Command("newteacher"))
async def teacher_start(event: Message | CallbackQuery, state: FSMContext):
    user = event.from_user
    if not user or not is_admin(user.id):
        await _safe_answer(event, "⛔")
        return
    await state.set_state(TeacherCreate.name)
    await _safe_answer(event, "ФИО преподавателя:")


@router.message(TeacherCreate.name)
async def teacher_name(message: Message, state: FSMContext):
    await state.update_data(name=(message.text or "").strip()[:255])
    await state.set_state(TeacherCreate.role)
    await message.answer("Должность / звание:")


@router.message(TeacherCreate.role)
async def teacher_role(message: Message, state: FSMContext):
    await state.update_data(role=(message.text or "").strip()[:255])
    await state.set_state(TeacherCreate.bio)
    await message.answer("Краткая биография (или /skip):")


@router.message(TeacherCreate.bio, Command("skip"))
async def teacher_bio_skip(message: Message, state: FSMContext):
    await state.update_data(bio="")
    await state.set_state(TeacherCreate.subjects)
    await message.answer("Преподаваемые предметы через запятую:")


@router.message(TeacherCreate.bio)
async def teacher_bio(message: Message, state: FSMContext):
    await state.update_data(bio=(message.text or "").strip())
    await state.set_state(TeacherCreate.subjects)
    await message.answer("Преподаваемые предметы через запятую:")


@router.message(TeacherCreate.subjects)
async def teacher_subjects(message: Message, state: FSMContext):
    subjects = [s.strip() for s in (message.text or "").split(",") if s.strip()]
    await state.update_data(subjects=subjects)
    await state.set_state(TeacherCreate.departments)
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="all"), KeyboardButton(text="music")],
            [KeyboardButton(text="theology"), KeyboardButton(text="theatre")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await message.answer(
        "Отделение(я) через запятую: <code>all</code>, <code>music</code>, <code>theology</code>, <code>theatre</code>",
        reply_markup=kb,
    )


@router.message(TeacherCreate.departments)
async def teacher_departments(message: Message, state: FSMContext):
    raw = (message.text or "all").strip()
    departments = [d.strip() for d in raw.split(",") if d.strip()] or ["all"]
    data = await state.get_data()
    name = cast(str, data.get("name", ""))
    initials = "".join(p[0].upper() for p in name.split()[:2]) if name else ""
    async with AsyncSessionLocal() as session:
        obj = models.Teacher(
            name=name,
            role=cast(str, data.get("role", "")),
            bio=cast(str, data.get("bio", "")),
            subjects=data.get("subjects", []),
            departments=departments,
            initials=initials,
            published=True,
        )
        session.add(obj)
        await session.commit()
    await state.clear()
    await message.answer("✅ Преподаватель добавлен.", reply_markup=ReplyKeyboardRemove())


# ============== Document creation (FSM) ==============

@router.callback_query(F.data == "adm:docs")
@router.message(Command("newdoc"))
async def doc_start(event: Message | CallbackQuery, state: FSMContext):
    user = event.from_user
    if not user or not is_admin(user.id):
        await _safe_answer(event, "⛔")
        return
    await state.set_state(DocumentCreate.title)
    await _safe_answer(event, "Название документа:")


@router.message(DocumentCreate.title)
async def doc_title(message: Message, state: FSMContext):
    await state.update_data(title=(message.text or "").strip()[:255])
    await state.set_state(DocumentCreate.file)
    await message.answer("Пришлите файл (PDF/DOCX/XLSX):")


@router.message(DocumentCreate.file, F.document)
async def doc_file(message: Message, state: FSMContext):
    if message.document is None:
        await message.answer("Это не документ. Попробуйте ещё раз.")
        return
    file_url = await _download_telegram_document(message)
    if not file_url:
        await message.answer("Не удалось сохранить файл.")
        return
    data = await state.get_data()
    async with AsyncSessionLocal() as session:
        obj = models.Document(
            title=data.get("title", message.document.file_name or "Документ"),
            file_url=file_url,
            published=True,
        )
        session.add(obj)
        await session.commit()
    await state.clear()
    await message.answer("✅ Документ загружен.")


# ============== Telegram file → uploads ==============

async def _download_telegram_photo(message: Message) -> str | None:
    if not message.photo:
        return None
    from ..config import UPLOADS_DIR
    from .bot import get_bot

    bot = get_bot()
    if bot is None:
        return None
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    if file.file_path is None:
        return None
    import secrets

    name = f"{secrets.token_urlsafe(16)}.jpg"
    target = UPLOADS_DIR / name
    await bot.download_file(file.file_path, destination=target)
    return f"/static/uploads/{name}"


async def _download_telegram_document(message: Message) -> str | None:
    if not message.document:
        return None
    from ..config import UPLOADS_DIR
    from .bot import get_bot

    bot = get_bot()
    if bot is None:
        return None
    file = await bot.get_file(message.document.file_id)
    if file.file_path is None:
        return None
    import secrets

    suffix = Path(message.document.file_name or "file").suffix.lower()
    if suffix not in {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".txt"}:
        return None
    name = f"{secrets.token_urlsafe(16)}{suffix}"
    target = UPLOADS_DIR / name
    await bot.download_file(file.file_path, destination=target)
    return f"/static/uploads/{name}"


# ============== Fallback ==============

@router.message()
async def fallback(message: Message):
    user = message.from_user
    if not user or not is_admin(user.id):
        await message.answer(
            "Этот бот только для администрации. Сайт колледжа: " + _public_url()
        )
        return
    await message.answer(
        "Не понял команду. Используйте /admin или /help.",
    )


# ============== Public registration ==============

def register(dp: Dispatcher) -> None:
    dp.include_router(router)
