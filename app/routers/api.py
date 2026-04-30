from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..services import create_application

router = APIRouter(prefix="/api")


class ApplicationIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    lastname: str = Field(default="", max_length=120)
    phone: str = Field(default="", max_length=120)
    program: str = Field(default="", max_length=64)
    church: str = Field(default="", max_length=255)
    note: str = Field(default="", max_length=2000)


@router.post("/applications")
async def submit_application(
    payload: ApplicationIn,
    session: AsyncSession = Depends(get_session),
):
    app = await create_application(session, payload.model_dump())

    # Notify admins via Telegram (fire-and-forget; don't fail the request if bot unavailable).
    import logging
    try:
        from ..bot.notifier import notify_new_application

        await notify_new_application(app)
    except Exception as exc:  # noqa: BLE001
        logging.getLogger("college.api").warning("notify_new_application failed: %s", exc)

    return {"ok": True, "id": app.id}


@router.get("/teachers")
async def get_teachers(session: AsyncSession = Depends(get_session)):
    from ..services import published_teachers

    teachers = await published_teachers(session)
    return [
        {
            "id": t.id,
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


@router.get("/site-info")
async def get_site_info(session: AsyncSession = Depends(get_session)):
    from ..services import get_settings_dict

    return await get_settings_dict(session)
