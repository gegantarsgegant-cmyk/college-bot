from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
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
