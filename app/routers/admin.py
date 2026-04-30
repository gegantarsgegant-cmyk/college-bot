from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import models
from ..auth import (
    SESSION_COOKIE,
    SESSION_MAX_AGE,
    current_admin,
    make_session_token,
)
from ..config import TEMPLATES_DIR
from ..db import get_session
from ..security import hash_password, verify_password
from ..services import (
    DEFAULT_SETTINGS,
    get_settings_dict,
    list_applications,
    set_setting,
    update_application_status,
)
from ..uploads import save_document, save_image

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _redirect_login() -> RedirectResponse:
    return RedirectResponse("/admin/login", status_code=303)


def _ensure_admin(request: Request) -> dict[str, Any]:
    admin = current_admin(request)
    if not admin:
        raise HTTPException(status_code=401, detail="auth required")
    return admin


# ----------------- Login / Logout -----------------

@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request, error: str = ""):
    return templates.TemplateResponse(
        request, "admin/login.html", {"error": error}
    )


@router.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    user = (
        await session.execute(
            select(models.AdminUser).where(models.AdminUser.username == username)
        )
    ).scalar_one_or_none()
    if not user or not verify_password(password, user.password_hash):
        return RedirectResponse("/admin/login?error=1", status_code=303)
    token = make_session_token(user.id, user.username)
    resp = RedirectResponse("/admin/", status_code=303)
    resp.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=False,
    )
    return resp


@router.post("/logout")
async def logout(request: Request):
    resp = RedirectResponse("/admin/login", status_code=303)
    resp.delete_cookie(SESSION_COOKIE)
    return resp


# ----------------- Dashboard -----------------

@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, session: AsyncSession = Depends(get_session)):
    admin = current_admin(request)
    if not admin:
        return _redirect_login()

    counts = {
        "applications_new": len(await list_applications(session, status="new")),
        "news": (
            await session.execute(select(models.News))
        ).scalars().all().__len__(),
        "events": (
            await session.execute(select(models.Event))
        ).scalars().all().__len__(),
        "teachers": (
            await session.execute(select(models.Teacher))
        ).scalars().all().__len__(),
        "gallery": (
            await session.execute(select(models.GalleryItem))
        ).scalars().all().__len__(),
        "documents": (
            await session.execute(select(models.Document))
        ).scalars().all().__len__(),
    }
    return templates.TemplateResponse(
        request, "admin/dashboard.html", {"admin": admin, "counts": counts}
    )


# ----------------- Applications -----------------

@router.get("/applications", response_class=HTMLResponse)
async def applications_list(
    request: Request,
    status: str = "",
    session: AsyncSession = Depends(get_session),
):
    admin = current_admin(request)
    if not admin:
        return _redirect_login()
    apps = await list_applications(session, status=status or None, limit=500)
    return templates.TemplateResponse(
        request,
        "admin/applications.html",
        {"admin": admin, "applications": apps, "status": status},
    )


@router.post("/applications/{app_id}/status")
async def applications_set_status(
    request: Request,
    app_id: int,
    new_status: str = Form(...),
    admin_comment: str = Form(""),
    session: AsyncSession = Depends(get_session),
):
    if not current_admin(request):
        return _redirect_login()
    if new_status not in {s.value for s in models.ApplicationStatus}:
        raise HTTPException(400, "Bad status")
    await update_application_status(session, app_id, new_status, admin_comment)
    return RedirectResponse("/admin/applications", status_code=303)


# ----------------- Generic CRUD helpers -----------------

async def _crud_list(
    request: Request,
    session: AsyncSession,
    model,
    template: str,
    extra_ctx: dict | None = None,
):
    admin = current_admin(request)
    if not admin:
        return _redirect_login()
    items = (await session.execute(select(model))).scalars().all()
    ctx = {"admin": admin, "items": items}
    if extra_ctx:
        ctx.update(extra_ctx)
    return templates.TemplateResponse(request, template, ctx)


# ----------------- News -----------------

@router.get("/news", response_class=HTMLResponse)
async def news_list(request: Request, session: AsyncSession = Depends(get_session)):
    return await _crud_list(request, session, models.News, "admin/news_list.html")


@router.post("/news/new")
async def news_create(
    request: Request,
    title: str = Form(...),
    body: str = Form(...),
    published: str = Form("on"),
    image: UploadFile | None = None,
    session: AsyncSession = Depends(get_session),
):
    if not current_admin(request):
        return _redirect_login()
    image_url = None
    if image and image.filename:
        image_url = save_image(image)
    obj = models.News(
        title=title,
        body=body,
        image_url=image_url,
        published=(published == "on"),
    )
    session.add(obj)
    await session.commit()
    return RedirectResponse("/admin/news", status_code=303)


@router.post("/news/{nid}/delete")
async def news_delete(request: Request, nid: int, session: AsyncSession = Depends(get_session)):
    if not current_admin(request):
        return _redirect_login()
    obj = await session.get(models.News, nid)
    if obj is not None:
        await session.delete(obj)
        await session.commit()
    return RedirectResponse("/admin/news", status_code=303)


# ----------------- Events -----------------

@router.get("/events", response_class=HTMLResponse)
async def events_list(request: Request, session: AsyncSession = Depends(get_session)):
    return await _crud_list(request, session, models.Event, "admin/events_list.html")


@router.post("/events/new")
async def events_create(
    request: Request,
    title: str = Form(...),
    starts_at: str = Form(...),
    description: str = Form(""),
    location: str = Form(""),
    published: str = Form("on"),
    session: AsyncSession = Depends(get_session),
):
    if not current_admin(request):
        return _redirect_login()
    from datetime import datetime as _dt

    try:
        # browser sends datetime-local: YYYY-MM-DDTHH:MM
        dt = _dt.fromisoformat(starts_at)
    except ValueError:
        raise HTTPException(400, "Bad date") from None
    obj = models.Event(
        title=title,
        description=description,
        starts_at=dt,
        location=location,
        published=(published == "on"),
    )
    session.add(obj)
    await session.commit()
    return RedirectResponse("/admin/events", status_code=303)


@router.post("/events/{eid}/delete")
async def events_delete(request: Request, eid: int, session: AsyncSession = Depends(get_session)):
    if not current_admin(request):
        return _redirect_login()
    obj = await session.get(models.Event, eid)
    if obj is not None:
        await session.delete(obj)
        await session.commit()
    return RedirectResponse("/admin/events", status_code=303)


# ----------------- Teachers -----------------

@router.get("/teachers", response_class=HTMLResponse)
async def teachers_list(request: Request, session: AsyncSession = Depends(get_session)):
    return await _crud_list(request, session, models.Teacher, "admin/teachers_list.html")


@router.post("/teachers/new")
async def teachers_create(
    request: Request,
    name: str = Form(...),
    initials: str = Form(""),
    role: str = Form(""),
    bio: str = Form(""),
    subjects: str = Form(""),
    departments: str = Form("all"),
    sort_order: int = Form(0),
    published: str = Form("on"),
    photo: UploadFile | None = None,
    session: AsyncSession = Depends(get_session),
):
    if not current_admin(request):
        return _redirect_login()
    photo_url = None
    if photo and photo.filename:
        photo_url = save_image(photo)
    subjects_list = [s.strip() for s in subjects.split(",") if s.strip()]
    departments_list = [d.strip() for d in departments.split(",") if d.strip()] or ["all"]
    if not initials and name:
        parts = [p for p in name.split() if p]
        initials = "".join(p[0].upper() for p in parts[:2])
    obj = models.Teacher(
        name=name,
        initials=initials,
        role=role,
        bio=bio,
        subjects=subjects_list,
        departments=departments_list,
        sort_order=sort_order,
        photo_url=photo_url,
        published=(published == "on"),
    )
    session.add(obj)
    await session.commit()
    return RedirectResponse("/admin/teachers", status_code=303)


@router.post("/teachers/{tid}/delete")
async def teachers_delete(request: Request, tid: int, session: AsyncSession = Depends(get_session)):
    if not current_admin(request):
        return _redirect_login()
    obj = await session.get(models.Teacher, tid)
    if obj is not None:
        await session.delete(obj)
        await session.commit()
    return RedirectResponse("/admin/teachers", status_code=303)


# ----------------- Gallery -----------------

@router.get("/gallery", response_class=HTMLResponse)
async def gallery_list(request: Request, session: AsyncSession = Depends(get_session)):
    return await _crud_list(request, session, models.GalleryItem, "admin/gallery_list.html")


@router.post("/gallery/new")
async def gallery_create(
    request: Request,
    title: str = Form(""),
    sort_order: int = Form(0),
    published: str = Form("on"),
    image: UploadFile | None = None,
    session: AsyncSession = Depends(get_session),
):
    if not current_admin(request):
        return _redirect_login()
    if not image or not image.filename:
        raise HTTPException(400, "Image required")
    url = save_image(image)
    obj = models.GalleryItem(
        title=title,
        image_url=url,
        sort_order=sort_order,
        published=(published == "on"),
    )
    session.add(obj)
    await session.commit()
    return RedirectResponse("/admin/gallery", status_code=303)


@router.post("/gallery/{gid}/delete")
async def gallery_delete(request: Request, gid: int, session: AsyncSession = Depends(get_session)):
    if not current_admin(request):
        return _redirect_login()
    obj = await session.get(models.GalleryItem, gid)
    if obj is not None:
        await session.delete(obj)
        await session.commit()
    return RedirectResponse("/admin/gallery", status_code=303)


# ----------------- Documents -----------------

@router.get("/documents", response_class=HTMLResponse)
async def documents_list(request: Request, session: AsyncSession = Depends(get_session)):
    return await _crud_list(request, session, models.Document, "admin/documents_list.html")


@router.post("/documents/new")
async def documents_create(
    request: Request,
    title: str = Form(...),
    description: str = Form(""),
    sort_order: int = Form(0),
    published: str = Form("on"),
    file: UploadFile | None = None,
    session: AsyncSession = Depends(get_session),
):
    if not current_admin(request):
        return _redirect_login()
    if not file or not file.filename:
        raise HTTPException(400, "File required")
    url = save_document(file)
    obj = models.Document(
        title=title,
        description=description,
        file_url=url,
        sort_order=sort_order,
        published=(published == "on"),
    )
    session.add(obj)
    await session.commit()
    return RedirectResponse("/admin/documents", status_code=303)


@router.post("/documents/{did}/delete")
async def documents_delete(request: Request, did: int, session: AsyncSession = Depends(get_session)):
    if not current_admin(request):
        return _redirect_login()
    obj = await session.get(models.Document, did)
    if obj is not None:
        await session.delete(obj)
        await session.commit()
    return RedirectResponse("/admin/documents", status_code=303)


# ----------------- Settings -----------------

@router.get("/settings", response_class=HTMLResponse)
async def settings_get(request: Request, session: AsyncSession = Depends(get_session)):
    admin = current_admin(request)
    if not admin:
        return _redirect_login()
    return templates.TemplateResponse(
        request,
        "admin/settings.html",
        {
            "admin": admin,
            "site": await get_settings_dict(session),
            "keys": list(DEFAULT_SETTINGS.keys()),
        },
    )


@router.post("/settings")
async def settings_save(request: Request, session: AsyncSession = Depends(get_session)):
    if not current_admin(request):
        return _redirect_login()
    form = await request.form()
    for k in DEFAULT_SETTINGS:
        if k in form:
            await set_setting(session, k, str(form[k]))
    return RedirectResponse("/admin/settings", status_code=303)


# ----------------- Change password -----------------

@router.post("/change-password")
async def change_password(
    request: Request,
    new_password: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    admin = current_admin(request)
    if not admin:
        return _redirect_login()
    user = await session.get(models.AdminUser, admin["uid"])
    if user is None:
        return _redirect_login()
    if len(new_password) < 6:
        raise HTTPException(400, "Пароль слишком короткий (мин. 6 символов)")
    user.password_hash = hash_password(new_password)
    await session.commit()
    return RedirectResponse("/admin/", status_code=303)
