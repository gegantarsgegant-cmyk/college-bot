from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import models
from ..config import TEMPLATES_DIR, UPLOADS_DIR, settings
from ..db import get_session
from ..security import verify_password
from ..services import (
    get_settings_dict,
    latest_news,
    published_documents,
    published_gallery,
    published_teachers,
    upcoming_events,
)

router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


_BR_RE = re.compile(r"<\s*br\s*/?\s*>", re.IGNORECASE)


def nl2br(value: str | None) -> Markup:
    """Render multi-line settings as HTML: escape, then turn \\n and literal
    <br> tags entered by admins into real <br> elements."""
    if not value:
        return Markup("")
    # Normalise both real newlines and admin-entered <br> tags to a sentinel,
    # escape everything, then put real <br> back.
    text = _BR_RE.sub("\n", str(value))
    escaped = escape(text)
    return Markup(str(escaped).replace("\n", "<br>"))


templates.env.filters["nl2br"] = nl2br


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, session: AsyncSession = Depends(get_session)):
    site = await get_settings_dict(session)
    teachers = await published_teachers(session)
    teachers_data = [
        {
            "initials": t.initials,
            "name": t.name,
            "role": t.role,
            "bio": t.bio,
            "subjects": t.subjects or [],
            "departments": t.departments or ["all"],
            "photo_url": t.photo_url,
        }
        for t in teachers
    ]
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "site": site,
            "news": await latest_news(session, limit=4),
            "events": await upcoming_events(session, limit=8),
            "teachers": teachers_data,
            "gallery": await published_gallery(session),
            "documents": await published_documents(session),
            "PUBLIC_URL": settings.PUBLIC_URL,
            "BOT_USERNAME": "",  # filled in via /api/site-info if you want a Mini App link
        },
    )


@router.get("/healthz", response_class=HTMLResponse)
async def health() -> str:
    return "ok"


# ---------------- Public file-share download page ----------------

async def _get_doc_by_slug(slug: str, session: AsyncSession) -> models.Document:
    obj = (
        await session.execute(select(models.Document).where(models.Document.slug == slug))
    ).scalar_one_or_none()
    if obj is None or not obj.published:
        raise HTTPException(404, "Файл не найден")
    return obj


def _is_exhausted(d: models.Document) -> bool:
    return bool(d.max_downloads) and (d.download_count or 0) >= d.max_downloads


@router.get("/d/{slug}", response_class=HTMLResponse)
async def file_share_page(
    request: Request,
    slug: str,
    session: AsyncSession = Depends(get_session),
):
    d = await _get_doc_by_slug(slug, session)
    site = await get_settings_dict(session)
    return templates.TemplateResponse(
        request,
        "file_share.html",
        {
            "doc": d,
            "site": site,
            "exhausted": _is_exhausted(d),
            "error": None,
        },
    )


@router.post("/d/{slug}/download")
async def file_share_download(
    request: Request,
    slug: str,
    password: str = Form(""),
    session: AsyncSession = Depends(get_session),
):
    d = await _get_doc_by_slug(slug, session)
    site = await get_settings_dict(session)
    if _is_exhausted(d):
        return templates.TemplateResponse(
            request,
            "file_share.html",
            {"doc": d, "site": site, "exhausted": True, "error": None},
            status_code=410,
        )
    if d.password_hash:
        if not password or not verify_password(password, d.password_hash):
            return templates.TemplateResponse(
                request,
                "file_share.html",
                {"doc": d, "site": site, "exhausted": False, "error": "Неверный пароль"},
                status_code=401,
            )
    d.download_count = (d.download_count or 0) + 1
    await session.commit()
    fname = (d.file_url or "").rsplit("/", 1)[-1]
    fpath = UPLOADS_DIR / fname
    if not fpath.is_file():
        raise HTTPException(404, "Файл отсутствует на сервере")
    return FileResponse(
        path=str(fpath),
        filename=d.original_filename or fname,
        media_type=d.mime_type or "application/octet-stream",
    )
