from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import TEMPLATES_DIR, settings
from ..db import get_session
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
