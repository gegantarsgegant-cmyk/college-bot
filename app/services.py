"""Business logic shared by web routes and the Telegram bot."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import models
from .security import hash_password

# ---------------- Settings ----------------

DEFAULT_SETTINGS: dict[str, str] = {
    "site_title": "Библейский Колледж ХВЕ",
    "hero_eyebrow": "Духовное учебное заведение · Минск, Беларусь",
    "hero_subtitle": "Бог ищет лидеров будущих перемен",
    "contact_address": "220092, г. Минск, ул. Бельского, 15, оф. 103\nрядом со ст. м. «Спортивная»",
    "contact_email": "cfnbel@gmail.com — приёмная комиссия\nadmin@biblecollege.by — администратор",
    "contact_phones": "+375 17 393 53 94\n+375 29 602 32 32\n+375 33 660 32 32",
    "contact_hours": "Понедельник — пятница\n10:00 – 18:00",
    "social_instagram": "https://www.instagram.com/xdn_college/",
    "social_telegram": "https://t.me/cfnbel",
    "social_vk": "https://vk.com/biblecollege",
    "social_facebook": "https://www.facebook.com/biblecollegeby/",
    "social_viber": "viber://chat?number=375336603232",
    "footer_email": "cfnbel@gmail.com",
    "footer_phone": "+375 17 393 53 94",
    "stats_directions": "3",
    "stats_years": "30+",
    "stats_degrees": "5+",
    "stats_callings": "∞",
}


async def get_settings_dict(session: AsyncSession) -> dict[str, str]:
    """Return all settings as a dict, with defaults filled in."""
    rows = (await session.execute(select(models.Setting))).scalars().all()
    out = dict(DEFAULT_SETTINGS)
    for r in rows:
        out[r.key] = r.value
    return out


async def set_setting(session: AsyncSession, key: str, value: str) -> None:
    obj = await session.get(models.Setting, key)
    if obj is None:
        session.add(models.Setting(key=key, value=value))
    else:
        obj.value = value
    await session.commit()


# ---------------- Bootstrap ----------------

async def ensure_admin_user(session: AsyncSession, username: str, password: str) -> None:
    existing = (
        await session.execute(select(models.AdminUser).where(models.AdminUser.username == username))
    ).scalar_one_or_none()
    if existing is None:
        session.add(
            models.AdminUser(username=username, password_hash=hash_password(password))
        )
        await session.commit()


async def ensure_default_settings(session: AsyncSession) -> None:
    existing = {
        r.key for r in (await session.execute(select(models.Setting))).scalars().all()
    }
    for k, v in DEFAULT_SETTINGS.items():
        if k not in existing:
            session.add(models.Setting(key=k, value=v))
    await session.commit()


async def ensure_default_teachers(session: AsyncSession) -> None:
    """Seed teachers from the original site template on first run only."""
    count = (
        await session.execute(select(models.Teacher.id).limit(1))
    ).scalar_one_or_none()
    if count is not None:
        return
    from .seed_teachers import DEFAULT_TEACHERS

    for i, t in enumerate(DEFAULT_TEACHERS):
        session.add(
            models.Teacher(
                name=t["name"],
                initials=t.get("initials", ""),
                role=t.get("role", ""),
                bio=t.get("bio", ""),
                subjects=t.get("subjects", []),
                departments=t.get("departments", ["all"]),
                photo_url=None,
                sort_order=i,
                published=True,
            )
        )
    await session.commit()


# ---------------- Applications ----------------

async def create_application(session: AsyncSession, data: dict[str, Any]) -> models.Application:
    obj = models.Application(
        name=(data.get("name") or "").strip()[:120],
        lastname=(data.get("lastname") or "").strip()[:120],
        phone=(data.get("phone") or "").strip()[:120],
        program=(data.get("program") or "").strip()[:64],
        church=(data.get("church") or "").strip()[:255],
        note=(data.get("note") or "").strip(),
    )
    session.add(obj)
    await session.commit()
    await session.refresh(obj)
    return obj


async def list_applications(
    session: AsyncSession,
    *,
    status: str | None = None,
    limit: int = 200,
) -> list[models.Application]:
    stmt = select(models.Application).order_by(models.Application.created_at.desc()).limit(limit)
    if status:
        stmt = stmt.where(models.Application.status == status)
    return list((await session.execute(stmt)).scalars().all())


async def application_stats(session: AsyncSession) -> dict[str, int]:
    """Counts of applications per status, plus total."""
    from sqlalchemy import func

    rows = (
        await session.execute(
            select(models.Application.status, func.count(models.Application.id))
            .group_by(models.Application.status)
        )
    ).all()
    counts = {s.value: 0 for s in models.ApplicationStatus}
    for status, n in rows:
        counts[status] = n
    counts["total"] = sum(counts.values())
    return counts


async def update_application_status(
    session: AsyncSession, app_id: int, status: str, admin_comment: str = ""
) -> models.Application | None:
    obj = await session.get(models.Application, app_id)
    if obj is None:
        return None
    obj.status = status
    if admin_comment:
        obj.admin_comment = admin_comment
    await session.commit()
    await session.refresh(obj)
    return obj


# ---------------- News / Events / Teachers / Gallery / Documents ----------------

async def latest_news(session: AsyncSession, limit: int = 5) -> list[models.News]:
    stmt = (
        select(models.News)
        .where(models.News.published.is_(True))
        .order_by(models.News.created_at.desc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


async def upcoming_events(session: AsyncSession, limit: int = 10) -> list[models.Event]:
    stmt = (
        select(models.Event)
        .where(models.Event.published.is_(True))
        .where(models.Event.starts_at >= datetime.utcnow())
        .order_by(models.Event.starts_at.asc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


async def published_teachers(session: AsyncSession) -> list[models.Teacher]:
    stmt = (
        select(models.Teacher)
        .where(models.Teacher.published.is_(True))
        .order_by(models.Teacher.sort_order.asc(), models.Teacher.id.asc())
    )
    return list((await session.execute(stmt)).scalars().all())


async def published_gallery(session: AsyncSession) -> list[models.GalleryItem]:
    stmt = (
        select(models.GalleryItem)
        .where(models.GalleryItem.published.is_(True))
        .order_by(models.GalleryItem.sort_order.asc(), models.GalleryItem.id.asc())
    )
    return list((await session.execute(stmt)).scalars().all())


async def published_documents(session: AsyncSession) -> list[models.Document]:
    stmt = (
        select(models.Document)
        .where(models.Document.published.is_(True))
        .order_by(models.Document.sort_order.asc(), models.Document.id.asc())
    )
    return list((await session.execute(stmt)).scalars().all())
