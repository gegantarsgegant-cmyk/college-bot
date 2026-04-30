"""Telegram bot handlers — public commands + admin content management."""

from __future__ import annotations

import logging
from html import escape
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
    WebAppInfo,
)

from .. import models
from ..config import settings
from ..db import AsyncSessionLocal
from ..services import (
    create_application,
    get_settings_dict,
    latest_news,
    list_applications,
    published_documents,
    published_teachers,
    upcoming_events,
    update_application_status,
)
from .states import ApplyFlow, DocumentCreate, EventCreate, NewsCreate, TeacherCreate

log = logging.getLogger("college.bot.handlers")
router = Router(name="college")


# --------------- Helpers ---------------

def is_admin(user_id: int) -> bool:
    return user_id in settings.admin_ids


def main_menu(user_id: int) -> ReplyKeyboardMarkup:
    rows: list[list[KeyboardButton]] = [
        [KeyboardButton(text="📰 Новости"), KeyboardButton(text="📅 События")],
        [KeyboardButton(text="🎓 Программы"), KeyboardButton(text="👥 Преподаватели")],
        [KeyboardButton(text="📄 Документы"), KeyboardButton(text="📍 Контакты")],
        [KeyboardButton(text="✍ Подать заявку")],
    ]
    if settings.PUBLIC_URL.startswith("https://"):
        rows.append(
            [
                KeyboardButton(
                    text="🌐 Открыть сайт",
                    web_app=WebAppInfo(url=settings.PUBLIC_URL),
                )
            ]
        )
    if is_admin(user_id):
        rows.append([KeyboardButton(text="⚙ Админ-панель")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def admin_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📥 Заявки", callback_data="adm:apps")],
            [
                InlineKeyboardButton(text="📰 Новости", callback_data="adm:news"),
                InlineKeyboardButton(text="📅 События", callback_data="adm:events"),
            ],
            [
                InlineKeyboardButton(text="👥 Преподаватели", callback_data="adm:teachers"),
                InlineKeyboardButton(text="📄 Документы", callback_data="adm:docs"),
            ],
            [InlineKeyboardButton(text="❌ Закрыть", callback_data="adm:close")],
        ]
    )


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


# --------------- Public commands ---------------

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await _ensure_bot_user(message)
    name = (message.from_user.first_name if message.from_user else "") or "друг"
    text = (
        f"<b>Здравствуйте, {escape(name)}!</b>\n\n"
        "Это бот <b>Библейского Колледжа ХВЕ</b>. Здесь вы можете:\n"
        "• читать новости и узнавать о событиях;\n"
        "• посмотреть программы и состав преподавателей;\n"
        "• скачать документы;\n"
        "• подать заявку на поступление прямо в Telegram.\n\n"
        "Выберите раздел в меню ниже 👇"
    )
    await message.answer(text, reply_markup=main_menu(message.from_user.id if message.from_user else 0))


@router.message(Command("help"))
async def cmd_help(message: Message):
    text = (
        "<b>Команды</b>\n"
        "/start — главное меню\n"
        "/news — последние новости\n"
        "/events — ближайшие события\n"
        "/programs — программы обучения\n"
        "/teachers — преподаватели\n"
        "/contacts — контакты\n"
        "/apply — подать заявку\n"
    )
    if message.from_user and is_admin(message.from_user.id):
        text += (
            "\n<b>Админ</b>\n"
            "/admin — админ-меню\n"
            "/applications — список заявок\n"
            "/newpost — добавить новость\n"
            "/newevent — добавить событие\n"
            "/newteacher — добавить преподавателя\n"
            "/newdoc — добавить документ\n"
            "/cancel — отменить текущую операцию\n"
        )
    await message.answer(text)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.", reply_markup=main_menu(message.from_user.id if message.from_user else 0))


@router.message(F.text == "📰 Новости")
@router.message(Command("news"))
async def show_news(message: Message):
    async with AsyncSessionLocal() as session:
        items = await latest_news(session, limit=5)
    if not items:
        await message.answer("Пока новостей нет.")
        return
    for n in items:
        text = f"<b>{escape(n.title)}</b>\n\n{escape(n.body)}"
        if n.image_url:
            url = settings.PUBLIC_URL.rstrip("/") + n.image_url
            try:
                await message.answer_photo(photo=url, caption=text[:1000])
                continue
            except Exception:  # noqa: BLE001
                pass
        await message.answer(text)


@router.message(F.text == "📅 События")
@router.message(Command("events"))
async def show_events(message: Message):
    async with AsyncSessionLocal() as session:
        items = await upcoming_events(session, limit=10)
    if not items:
        await message.answer("Ближайших событий не запланировано.")
        return
    lines = ["<b>📅 Ближайшие события</b>\n"]
    for ev in items:
        when = ev.starts_at.strftime("%d.%m.%Y %H:%M")
        lines.append(f"• <b>{when}</b> — {escape(ev.title)}")
        if ev.location:
            lines.append(f"  📍 {escape(ev.location)}")
        if ev.description:
            lines.append(f"  {escape(ev.description)[:200]}")
    await message.answer("\n".join(lines))


@router.message(F.text == "🎓 Программы")
@router.message(Command("programs"))
async def show_programs(message: Message):
    text = (
        "<b>🎓 Программы подготовки</b>\n\n"
        "<b>1. Музыкальное служение</b> — Бакалавр искусств в церковной музыке.\n"
        "Очно-заочная форма, 4 сессии в год. Уровень 1 — 3 года, Уровень 2 — 2,5 года.\n\n"
        "<b>2. Богословие и христианское служение</b> — Сертификат / Бакалавр служения / Бакалавр богословия.\n"
        "Заочная (онлайн).\n\n"
        "<b>3. Театральное служение</b> — Бакалавр искусств в театральном служении.\n"
        "Очно-заочная форма, 4 сессии в год. 3 года.\n"
    )
    await message.answer(text)


@router.message(F.text == "👥 Преподаватели")
@router.message(Command("teachers"))
async def show_teachers(message: Message):
    async with AsyncSessionLocal() as session:
        items = await published_teachers(session)
    if not items:
        await message.answer("Состав преподавателей пока не добавлен.")
        return
    lines = [f"<b>👥 Преподаватели ({len(items)})</b>\n"]
    for t in items[:30]:
        lines.append(f"• <b>{escape(t.name)}</b> — {escape(t.role)}")
    if len(items) > 30:
        lines.append(f"\n…и ещё {len(items) - 30}. Полный список — на сайте.")
    await message.answer("\n".join(lines))


@router.message(F.text == "📄 Документы")
@router.message(Command("documents"))
async def show_documents(message: Message):
    async with AsyncSessionLocal() as session:
        items = await published_documents(session)
    if not items:
        await message.answer("Документы пока не загружены.")
        return
    base = settings.PUBLIC_URL.rstrip("/")
    lines = ["<b>📄 Документы</b>\n"]
    for d in items:
        url = base + d.file_url if d.file_url.startswith("/") else d.file_url
        lines.append(f"• <a href=\"{url}\">{escape(d.title)}</a>")
        if d.description:
            lines.append(f"  {escape(d.description)[:200]}")
    await message.answer("\n".join(lines), disable_web_page_preview=True)


@router.message(F.text == "📍 Контакты")
@router.message(Command("contacts"))
async def show_contacts(message: Message):
    async with AsyncSessionLocal() as session:
        site = await get_settings_dict(session)
    text = (
        "<b>📍 Контакты</b>\n\n"
        f"<b>Адрес:</b>\n{escape(site.get('contact_address',''))}\n\n"
        f"<b>Email:</b>\n{escape(site.get('contact_email',''))}\n\n"
        f"<b>Телефоны:</b>\n{escape(site.get('contact_phones',''))}\n\n"
        f"<b>Режим работы:</b>\n{escape(site.get('contact_hours',''))}"
    )
    await message.answer(text)


# --------------- Apply flow ---------------

@router.message(F.text == "✍ Подать заявку")
@router.message(Command("apply"))
async def apply_start(message: Message, state: FSMContext):
    await state.set_state(ApplyFlow.name)
    await message.answer("Как вас зовут? (Имя)")


@router.message(ApplyFlow.name)
async def apply_name(message: Message, state: FSMContext):
    await state.update_data(name=(message.text or "").strip())
    await state.set_state(ApplyFlow.lastname)
    await message.answer("Ваша фамилия?")


@router.message(ApplyFlow.lastname)
async def apply_lastname(message: Message, state: FSMContext):
    await state.update_data(lastname=(message.text or "").strip())
    await state.set_state(ApplyFlow.phone)
    await message.answer("Телефон или Telegram для связи:")


@router.message(ApplyFlow.phone)
async def apply_phone(message: Message, state: FSMContext):
    await state.update_data(phone=(message.text or "").strip())
    await state.set_state(ApplyFlow.program)
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Музыкальное служение")],
            [KeyboardButton(text="Богословие и христианское служение")],
            [KeyboardButton(text="Театральное служение")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await message.answer("Какая программа вас интересует?", reply_markup=kb)


_PROGRAM_MAP = {
    "Музыкальное служение": "music",
    "Богословие и христианское служение": "theology",
    "Театральное служение": "theatre",
}


@router.message(ApplyFlow.program)
async def apply_program(message: Message, state: FSMContext):
    raw = (message.text or "").strip()
    await state.update_data(program=_PROGRAM_MAP.get(raw, raw)[:64])
    await state.set_state(ApplyFlow.church)
    await message.answer("Ваша церковь (название и город). Можно «—», если не указываете.")


@router.message(ApplyFlow.church)
async def apply_church(message: Message, state: FSMContext):
    data = await state.get_data()
    church = (message.text or "").strip()
    if church == "—":
        church = ""
    payload = {**data, "church": church}
    async with AsyncSessionLocal() as session:
        app = await create_application(session, payload)
    await state.clear()
    await message.answer(
        f"✅ Заявка #{app.id} принята! Мы свяжемся с вами в течение 1–2 рабочих дней.",
        reply_markup=main_menu(message.from_user.id if message.from_user else 0),
    )

    # Notify admins
    try:
        from .notifier import notify_new_application

        await notify_new_application(app)
    except Exception as exc:  # noqa: BLE001
        log.warning("Notify failed: %s", exc)


# --------------- Admin panel ---------------

@router.message(F.text == "⚙ Админ-панель")
@router.message(Command("admin"))
async def admin_panel(message: Message):
    if not message.from_user or not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ только для администраторов.")
        return
    await message.answer("⚙ <b>Админ-панель</b>", reply_markup=admin_menu())


@router.callback_query(F.data == "adm:close")
async def admin_close(cb: CallbackQuery):
    if cb.message:
        try:
            await cb.message.delete()
        except Exception:  # noqa: BLE001
            pass
    await cb.answer()


@router.callback_query(F.data == "adm:apps")
@router.message(Command("applications"))
async def admin_apps(event: Message | CallbackQuery):
    user = event.from_user
    if not user or not is_admin(user.id):
        await _safe_answer(event, "⛔ Доступ только для администраторов.")
        return
    async with AsyncSessionLocal() as session:
        apps = await list_applications(session, status="new", limit=10)
    if not apps:
        await _safe_answer(event, "Новых заявок нет 🎉")
        return
    for app in apps:
        text = (
            f"<b>📥 Заявка #{app.id}</b>\n"
            f"<b>{escape(app.name)} {escape(app.lastname)}</b>\n"
            f"📞 {escape(app.phone)}\n"
            f"🎓 {escape(app.program)}\n"
            f"⛪ {escape(app.church) or '—'}"
        )
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✓ В работу", callback_data=f"app:in_progress:{app.id}"),
                    InlineKeyboardButton(text="✓ Принято", callback_data=f"app:accepted:{app.id}"),
                    InlineKeyboardButton(text="✗ Отклонить", callback_data=f"app:rejected:{app.id}"),
                ]
            ]
        )
        target = event.message if isinstance(event, CallbackQuery) else event
        if target:
            await target.answer(text, reply_markup=kb)
    if isinstance(event, CallbackQuery):
        await event.answer()


async def _safe_answer(event: Message | CallbackQuery, text: str):
    if isinstance(event, CallbackQuery):
        if event.message:
            await event.message.answer(text)
        await event.answer()
    else:
        await event.answer(text)


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
    if cb.message:
        try:
            await cb.message.edit_reply_markup(reply_markup=None)
            await cb.message.answer(
                f"Заявка #{app.id}: статус → <b>{label_map.get(status, status)}</b>"
            )
        except Exception:  # noqa: BLE001
            pass
    await cb.answer("Готово")


# ----- News creation -----

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


# ----- Event creation -----

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
    await message.answer("Дата и время? Формат: <code>ДД.ММ.ГГГГ ЧЧ:ММ</code> (например, 15.09.2026 18:00)")


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


# ----- Teacher creation -----

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
    await message.answer(
        "✅ Преподаватель добавлен.",
        reply_markup=main_menu(message.from_user.id if message.from_user else 0),
    )


# ----- Document creation -----

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
        await message.answer("Не удалось сохранить файл. Попробуйте ещё раз.")
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


# --------------- Telegram file → uploads ---------------

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

    suffix = ".jpg"
    name = f"{secrets.token_urlsafe(16)}{suffix}"
    target = UPLOADS_DIR / name
    await bot.download_file(file.file_path, destination=target)
    return f"/static/uploads/{name}"


async def _download_telegram_document(message: Message) -> str | None:
    if not message.document:
        return None
    from pathlib import Path

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


# --------------- Fallback ---------------

@router.message()
async def fallback(message: Message):
    await message.answer(
        "Не понял команду. Используйте меню или /help.",
        reply_markup=main_menu(message.from_user.id if message.from_user else 0),
    )


# --------------- Public registration ---------------

def register(dp: Dispatcher) -> None:
    dp.include_router(router)
