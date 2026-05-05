from __future__ import annotations

import re
import secrets as _secrets
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
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
    LOCALIZED_LANGS,
    application_stats,
    get_settings_all_langs,
    get_settings_dict,
    list_applications,
    set_setting,
    update_application_status,
)
from ..uploads import save_document, save_image, save_shared_file  # noqa: F401

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
# Reuse filters defined on the public-site Jinja env (e.g. nl2br) so the admin
# can render the public homepage in edit mode.
from .site import nl2br as _nl2br  # noqa: E402

templates.env.filters["nl2br"] = _nl2br
templates.env.globals["now"] = lambda: datetime.utcnow()

from ..i18n import register_jinja as _register_i18n  # noqa: E402

_register_i18n(templates.env)


def _redirect_login() -> RedirectResponse:
    return RedirectResponse("/admin/login", status_code=303)


async def _new_apps_count(session: AsyncSession) -> int:
    from sqlalchemy import func

    return int(
        (
            await session.execute(
                select(func.count(models.Application.id)).where(
                    models.Application.status == models.ApplicationStatus.new.value
                )
            )
        ).scalar_one()
    )


async def _render(
    request: Request,
    session: AsyncSession,
    template: str,
    ctx: dict[str, Any] | None = None,
):
    """TemplateResponse wrapper that always injects `admin` + `new_apps_count`."""
    admin = current_admin(request)
    if not admin:
        return _redirect_login()
    full = {
        "admin": admin,
        "new_apps_count": await _new_apps_count(session),
    }
    if ctx:
        full.update(ctx)
    return templates.TemplateResponse(request, template, full)


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


# ----------------- Telegram Mini App auto-login -----------------

@router.get("/tg", response_class=HTMLResponse)
async def tg_auth_page(request: Request):
    """HTML-страница, которую открывает Telegram Mini App.

    Внутри страницы JavaScript читает Telegram.WebApp.initData и POSTит её
    на /admin/tg/auth, после чего получает session cookie и переходит на /admin/.
    """
    return templates.TemplateResponse(request, "admin/tg_auth.html", {})


@router.post("/tg/auth")
async def tg_auth_submit(
    request: Request,
    init_data: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    """Проверяет HMAC-подпись Telegram WebApp initData и выдаёт session cookie."""
    from ..config import settings as app_settings
    from ..tg_webapp import parse_and_verify_init_data

    if not app_settings.TELEGRAM_BOT_TOKEN:
        raise HTTPException(503, "Bot is not configured")

    parsed = parse_and_verify_init_data(init_data, app_settings.TELEGRAM_BOT_TOKEN)
    if parsed is None:
        raise HTTPException(401, "Invalid Telegram signature")

    user = parsed.get("user") or {}
    tg_user_id = user.get("id")
    if not isinstance(tg_user_id, int) or tg_user_id not in app_settings.admin_ids:
        raise HTTPException(403, "Этот аккаунт не в списке администраторов колледжа.")

    # Mirror admin in DB so /admin/ has something to render.
    username = user.get("username") or f"tg_{tg_user_id}"
    existing = (
        await session.execute(
            select(models.AdminUser).where(models.AdminUser.username == username)
        )
    ).scalar_one_or_none()
    if existing is None:
        new_admin = models.AdminUser(
            username=username,
            password_hash=hash_password("!disabled-tg-only!"),
        )
        session.add(new_admin)
        await session.commit()
        await session.refresh(new_admin)
        existing = new_admin

    token = make_session_token(existing.id, existing.username)
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


# ----------------- Dashboard -----------------

@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, session: AsyncSession = Depends(get_session)):
    if not current_admin(request):
        return _redirect_login()

    from sqlalchemy import func

    async def _count(model) -> int:
        return int(
            (await session.execute(select(func.count(model.id)))).scalar_one()
        )

    apps = await application_stats(session)
    counts = {
        "apps": apps,
        "news": await _count(models.News),
        "events": await _count(models.Event),
        "teachers": await _count(models.Teacher),
        "gallery": await _count(models.GalleryItem),
        "documents": await _count(models.Document),
    }
    recent_apps = await list_applications(session, limit=5)
    return await _render(
        request, session, "admin/dashboard.html",
        {"counts": counts, "recent_apps": recent_apps},
    )


# ----------------- Applications (CRM) -----------------

def _parse_date(s: str):
    from datetime import datetime as _dt

    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return _dt.strptime(s, fmt)
        except ValueError:
            pass
    return None


@router.get("/applications", response_class=HTMLResponse)
async def applications_list(
    request: Request,
    status: str = "",
    program: str = "",
    q: str = "",
    date_from: str = "",
    date_to: str = "",
    view: str = "kanban",
    session: AsyncSession = Depends(get_session),
):
    if not current_admin(request):
        return _redirect_login()
    df = _parse_date(date_from)
    dt_ = _parse_date(date_to)
    if dt_ is not None:
        # include the whole "to" day
        from datetime import timedelta as _td
        dt_ = dt_ + _td(days=1)
    apps = await list_applications(
        session,
        status=status or None,
        program=program or None,
        date_from=df,
        date_to=dt_,
        search=q or None,
        limit=1000,
    )
    stats = await application_stats(session)
    # Group by status for kanban view, preserving the funnel order.
    grouped: dict[str, list] = {s.value: [] for s in models.ApplicationStatus}
    for a in apps:
        grouped.setdefault(a.status, []).append(a)
    # Distinct programs for the filter dropdown — pull titles from the table.
    programs = list(
        (
            await session.execute(
                select(models.Program.title)
                .where(models.Program.published.is_(True))
                .order_by(models.Program.sort_order.asc())
            )
        )
        .scalars()
        .all()
    )
    return await _render(
        request, session, "admin/applications.html",
        {
            "applications": apps,
            "grouped": grouped,
            "status": status,
            "program": program,
            "q": q,
            "date_from": date_from,
            "date_to": date_to,
            "view": view if view in {"kanban", "list"} else "kanban",
            "stats": stats,
            "programs_list": programs,
            "status_labels": models.STATUS_LABELS,
            "status_emoji": models.STATUS_EMOJI,
        },
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
    # AJAX request from the kanban board → return JSON; HTML form posts redirect.
    if (request.headers.get("X-Requested-With") or "").lower() == "fetch":
        return JSONResponse({"ok": True})
    return RedirectResponse("/admin/applications", status_code=303)


@router.get("/applications/{app_id}", response_class=HTMLResponse)
async def applications_detail(
    request: Request, app_id: int, session: AsyncSession = Depends(get_session)
):
    if not current_admin(request):
        return _redirect_login()
    obj = await session.get(models.Application, app_id)
    if obj is None:
        raise HTTPException(404)
    return JSONResponse(
        {
            "id": obj.id,
            "name": obj.name,
            "lastname": obj.lastname,
            "phone": obj.phone,
            "program": obj.program,
            "church": obj.church,
            "note": obj.note,
            "status": obj.status,
            "status_label": models.STATUS_LABELS.get(obj.status, obj.status),
            "admin_comment": obj.admin_comment,
            "tags": obj.tags or [],
            "assigned_to": obj.assigned_to or "",
            "history": obj.history or [],
            "last_contacted_at": (
                obj.last_contacted_at.isoformat() if obj.last_contacted_at else None
            ),
            "created_at": obj.created_at.isoformat() if obj.created_at else None,
        }
    )


@router.post("/applications/{app_id}/note")
async def applications_add_note(
    request: Request,
    app_id: int,
    note: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    if not current_admin(request):
        return _redirect_login()
    from ..services import add_application_note

    await add_application_note(session, app_id, note, who=current_admin(request) or "admin")
    if (request.headers.get("X-Requested-With") or "").lower() == "fetch":
        return JSONResponse({"ok": True})
    return RedirectResponse("/admin/applications", status_code=303)


@router.post("/applications/{app_id}/contact")
async def applications_mark_contact(
    request: Request, app_id: int, session: AsyncSession = Depends(get_session)
):
    if not current_admin(request):
        return _redirect_login()
    from ..services import mark_application_contacted

    await mark_application_contacted(session, app_id, who=current_admin(request) or "admin")
    return JSONResponse({"ok": True})


@router.post("/applications/{app_id}/tags")
async def applications_set_tags(
    request: Request,
    app_id: int,
    tags: str = Form(""),
    session: AsyncSession = Depends(get_session),
):
    if not current_admin(request):
        return _redirect_login()
    from ..services import update_application_tags

    parts = [t.strip() for t in tags.replace(";", ",").split(",")]
    await update_application_tags(session, app_id, parts, who=current_admin(request) or "admin")
    return JSONResponse({"ok": True})


@router.post("/applications/{app_id}/assign")
async def applications_set_assigned(
    request: Request,
    app_id: int,
    assigned_to: str = Form(""),
    session: AsyncSession = Depends(get_session),
):
    if not current_admin(request):
        return _redirect_login()
    from ..services import assign_application

    await assign_application(session, app_id, assigned_to, who=current_admin(request) or "admin")
    return JSONResponse({"ok": True})


@router.get("/applications.csv")
async def applications_export_csv(
    request: Request,
    status: str = "",
    program: str = "",
    q: str = "",
    date_from: str = "",
    date_to: str = "",
    session: AsyncSession = Depends(get_session),
):
    if not current_admin(request):
        return _redirect_login()
    import csv
    import io

    df = _parse_date(date_from)
    dt_ = _parse_date(date_to)
    if dt_ is not None:
        from datetime import timedelta as _td
        dt_ = dt_ + _td(days=1)
    apps = await list_applications(
        session,
        status=status or None,
        program=program or None,
        date_from=df,
        date_to=dt_,
        search=q or None,
        limit=10_000,
    )
    buf = io.StringIO()
    # UTF-8 BOM for Excel
    buf.write("\ufeff")
    writer = csv.writer(buf, delimiter=";")
    writer.writerow([
        "ID", "Дата", "Имя", "Фамилия", "Телефон", "Программа",
        "Церковь", "Сообщение", "Статус", "Ответственный", "Теги",
        "Последний контакт", "Комментарий",
    ])
    for a in apps:
        writer.writerow([
            a.id,
            a.created_at.strftime("%d.%m.%Y %H:%M") if a.created_at else "",
            a.name, a.lastname, a.phone, a.program, a.church,
            (a.note or "").replace("\n", " "),
            models.STATUS_LABELS.get(a.status, a.status),
            a.assigned_to or "",
            ", ".join(a.tags or []),
            a.last_contacted_at.strftime("%d.%m.%Y %H:%M") if a.last_contacted_at else "",
            (a.admin_comment or "").replace("\n", " "),
        ])
    from datetime import datetime as _dt

    fname = f"applications-{_dt.utcnow():%Y%m%d-%H%M%S}.csv"
    from fastapi.responses import Response

    return Response(
        content=buf.getvalue().encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


# ----------------- Generic CRUD helpers -----------------

async def _crud_list(
    request: Request,
    session: AsyncSession,
    model,
    template: str,
    extra_ctx: dict | None = None,
):
    if not current_admin(request):
        return _redirect_login()
    items = (await session.execute(select(model))).scalars().all()
    ctx: dict[str, Any] = {"items": items}
    if extra_ctx:
        ctx.update(extra_ctx)
    return await _render(request, session, template, ctx)


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


@router.post("/teachers/{tid}/edit")
async def teachers_update(
    request: Request,
    tid: int,
    name: str = Form(...),
    initials: str = Form(""),
    role: str = Form(""),
    bio: str = Form(""),
    subjects: str = Form(""),
    departments: str = Form("all"),
    sort_order: int = Form(0),
    published: str = Form(""),
    photo: UploadFile | None = None,
    session: AsyncSession = Depends(get_session),
):
    if not current_admin(request):
        return _redirect_login()
    obj = await session.get(models.Teacher, tid)
    if obj is None:
        raise HTTPException(404, "Not found")
    if photo and photo.filename:
        obj.photo_url = save_image(photo)
    obj.name = name
    obj.initials = initials or "".join(p[0].upper() for p in name.split()[:2])
    obj.role = role
    obj.bio = bio
    obj.subjects = [s.strip() for s in subjects.split(",") if s.strip()]
    obj.departments = [d.strip() for d in departments.split(",") if d.strip()] or ["all"]
    obj.sort_order = sort_order
    obj.published = published == "on"
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


# ----------------- Programs -----------------

def _parse_lines(s: str) -> list[str]:
    return [ln.strip() for ln in (s or "").replace("\r", "").split("\n") if ln.strip()]


def _collect_i18n(form, fields: tuple[str, ...]) -> dict:
    """Pull localized variants of ``fields`` out of a form, returning
    ``{"be": {field: value, ...}, "en": {...}}`` with empty values dropped.
    Items named ``<field>__be`` / ``<field>__en`` map to that lang.
    Document-list fields ending in ``_lines`` are split on newlines.
    """
    i18n: dict[str, dict] = {}
    for lng in ("be", "en"):
        bucket: dict = {}
        for f in fields:
            key = f"{f}__{lng}"
            if key not in form:
                continue
            v = str(form[key]).strip()
            if not v:
                continue
            if f == "documents" or f == "subjects":
                bucket[f] = _parse_lines(v)
            else:
                bucket[f] = v
        if bucket:
            i18n[lng] = bucket
    return i18n


@router.get("/programs", response_class=HTMLResponse)
async def programs_list(request: Request, session: AsyncSession = Depends(get_session)):
    if not current_admin(request):
        return _redirect_login()
    progs = (
        await session.execute(
            select(models.Program).order_by(models.Program.sort_order, models.Program.id)
        )
    ).scalars().all()
    spec_rows = (
        await session.execute(
            select(models.ProgramSpecialty).order_by(
                models.ProgramSpecialty.program_id,
                models.ProgramSpecialty.sort_order,
                models.ProgramSpecialty.id,
            )
        )
    ).scalars().all()
    specs_by_program: dict[int, list] = {}
    for s in spec_rows:
        specs_by_program.setdefault(s.program_id, []).append(s)
    return await _render(
        request,
        session,
        "admin/programs_list.html",
        {"items": progs, "specs_by_program": specs_by_program},
    )


_PROGRAM_I18N_FIELDS = (
    "tag",
    "title",
    "description",
    "form_label",
    "term_label",
    "degree_label",
    "tuition_amount",
    "tuition_note",
    "documents",
)


@router.post("/programs/new")
async def programs_create(
    request: Request,
    slug: str = Form(...),
    number: str = Form(""),
    tag: str = Form(""),
    title: str = Form(...),
    description: str = Form(""),
    form_label: str = Form(""),
    term_label: str = Form(""),
    degree_label: str = Form(""),
    tuition_amount: str = Form(""),
    tuition_note: str = Form(""),
    documents: str = Form(""),
    sort_order: int = Form(0),
    published: str = Form("on"),
    session: AsyncSession = Depends(get_session),
):
    if not current_admin(request):
        return _redirect_login()
    form = await request.form()
    obj = models.Program(
        slug=slug.strip().lower()[:32],
        number=number.strip()[:8],
        tag=tag.strip()[:120],
        title=title.strip()[:255],
        description=description.strip(),
        form_label=form_label.strip()[:120],
        term_label=term_label.strip()[:255],
        degree_label=degree_label.strip()[:255],
        tuition_amount=tuition_amount.strip()[:64],
        tuition_note=tuition_note.strip()[:500],
        documents=_parse_lines(documents),
        sort_order=sort_order,
        published=(published == "on"),
        i18n=_collect_i18n(form, _PROGRAM_I18N_FIELDS),
    )
    session.add(obj)
    await session.commit()
    return RedirectResponse("/admin/programs", status_code=303)


@router.post("/programs/{pid}/edit")
async def programs_update(
    request: Request,
    pid: int,
    slug: str = Form(...),
    number: str = Form(""),
    tag: str = Form(""),
    title: str = Form(...),
    description: str = Form(""),
    form_label: str = Form(""),
    term_label: str = Form(""),
    degree_label: str = Form(""),
    tuition_amount: str = Form(""),
    tuition_note: str = Form(""),
    documents: str = Form(""),
    sort_order: int = Form(0),
    published: str = Form(""),
    session: AsyncSession = Depends(get_session),
):
    if not current_admin(request):
        return _redirect_login()
    obj = await session.get(models.Program, pid)
    if obj is None:
        raise HTTPException(404, "Not found")
    form = await request.form()
    obj.slug = slug.strip().lower()[:32]
    obj.number = number.strip()[:8]
    obj.tag = tag.strip()[:120]
    obj.title = title.strip()[:255]
    obj.description = description.strip()
    obj.form_label = form_label.strip()[:120]
    obj.term_label = term_label.strip()[:255]
    obj.degree_label = degree_label.strip()[:255]
    obj.tuition_amount = tuition_amount.strip()[:64]
    obj.tuition_note = tuition_note.strip()[:500]
    obj.documents = _parse_lines(documents)
    obj.sort_order = sort_order
    obj.published = (published == "on")
    obj.i18n = _collect_i18n(form, _PROGRAM_I18N_FIELDS)
    await session.commit()
    return RedirectResponse("/admin/programs", status_code=303)


@router.post("/programs/{pid}/delete")
async def programs_delete(
    request: Request, pid: int, session: AsyncSession = Depends(get_session)
):
    if not current_admin(request):
        return _redirect_login()
    obj = await session.get(models.Program, pid)
    if obj is not None:
        # also delete its specialties
        specs = (
            await session.execute(
                select(models.ProgramSpecialty).where(
                    models.ProgramSpecialty.program_id == pid
                )
            )
        ).scalars().all()
        for s in specs:
            await session.delete(s)
        await session.delete(obj)
        await session.commit()
    return RedirectResponse("/admin/programs", status_code=303)


@router.post("/programs/{pid}/specialties/new")
async def programs_specialty_create(
    request: Request,
    pid: int,
    num: str = Form(""),
    name: str = Form(...),
    subs: str = Form(""),
    qualification: str = Form(""),
    sort_order: int = Form(0),
    session: AsyncSession = Depends(get_session),
):
    if not current_admin(request):
        return _redirect_login()
    prog = await session.get(models.Program, pid)
    if prog is None:
        raise HTTPException(404, "Program not found")
    form = await request.form()
    session.add(
        models.ProgramSpecialty(
            program_id=pid,
            num=num.strip()[:8],
            name=name.strip()[:255],
            subs=subs.strip(),
            qualification=qualification.strip()[:500],
            sort_order=sort_order,
            i18n=_collect_i18n(form, ("name", "subs", "qualification")),
        )
    )
    await session.commit()
    return RedirectResponse("/admin/programs", status_code=303)


@router.post("/programs/{pid}/specialties/{sid}/edit")
async def programs_specialty_update(
    request: Request,
    pid: int,
    sid: int,
    num: str = Form(""),
    name: str = Form(...),
    subs: str = Form(""),
    qualification: str = Form(""),
    sort_order: int = Form(0),
    session: AsyncSession = Depends(get_session),
):
    if not current_admin(request):
        return _redirect_login()
    obj = await session.get(models.ProgramSpecialty, sid)
    if obj is None or obj.program_id != pid:
        raise HTTPException(404, "Specialty not found")
    form = await request.form()
    obj.num = num.strip()[:8]
    obj.name = name.strip()[:255]
    obj.subs = subs.strip()
    obj.qualification = qualification.strip()[:500]
    obj.sort_order = sort_order
    obj.i18n = _collect_i18n(form, ("name", "subs", "qualification"))
    await session.commit()
    return RedirectResponse("/admin/programs", status_code=303)


@router.post("/programs/{pid}/specialties/{sid}/delete")
async def programs_specialty_delete(
    request: Request,
    pid: int,
    sid: int,
    session: AsyncSession = Depends(get_session),
):
    if not current_admin(request):
        return _redirect_login()
    obj = await session.get(models.ProgramSpecialty, sid)
    if obj is not None and obj.program_id == pid:
        await session.delete(obj)
        await session.commit()
    return RedirectResponse("/admin/programs", status_code=303)


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


# ----------------- Documents (mini file-sharing service) -----------------


def _new_doc_slug() -> str:
    return _secrets.token_urlsafe(8)


def _gather_disk_info() -> dict[str, Any]:
    """Disk usage stats for the admin Files page."""
    import shutil
    from pathlib import Path

    from ..config import UPLOADS_DIR

    try:
        total, used, free = shutil.disk_usage(str(UPLOADS_DIR))
    except OSError:
        total = used = free = 0

    uploads_bytes = 0
    files_count = 0
    try:
        upath = Path(UPLOADS_DIR)
        if upath.exists():
            for p in upath.rglob("*"):
                if p.is_file():
                    try:
                        uploads_bytes += p.stat().st_size
                        files_count += 1
                    except OSError:
                        continue
    except OSError:
        pass

    pct = round(used * 100 / total, 1) if total else 0.0
    return {
        "total": total,
        "used": used,
        "free": free,
        "used_pct": pct,
        "uploads_bytes": uploads_bytes,
        "uploads_files_count": files_count,
    }


@router.get("/documents", response_class=HTMLResponse)
async def documents_list(request: Request, session: AsyncSession = Depends(get_session)):
    if not current_admin(request):
        return _redirect_login()
    rows = (
        await session.execute(
            select(models.Document).order_by(models.Document.created_at.desc())
        )
    ).scalars().all()
    return await _render(
        request, session, "admin/documents_list.html",
        {"items": rows, "disk": _gather_disk_info()},
    )


@router.post("/documents/new")
async def documents_create(
    request: Request,
    description: str = Form(""),
    title: str = Form(""),
    password: str = Form(""),
    max_downloads: str = Form(""),
    published: str = Form("on"),
    file: UploadFile | None = None,
    session: AsyncSession = Depends(get_session),
):
    if not current_admin(request):
        return _redirect_login()
    if not file or not file.filename:
        raise HTTPException(400, "File required")
    url, original_name, size_bytes, mime = save_shared_file(file)
    # Generate unique slug
    while True:
        slug = _new_doc_slug()
        existing = (
            await session.execute(select(models.Document).where(models.Document.slug == slug))
        ).scalar_one_or_none()
        if existing is None:
            break
    max_d_int: int | None = None
    if max_downloads.strip():
        try:
            v = int(max_downloads)
            max_d_int = v if v > 0 else None
        except ValueError:
            max_d_int = None
    obj = models.Document(
        title=(title.strip() or original_name)[:255],
        description=description.strip(),
        file_url=url,
        slug=slug,
        original_filename=original_name,
        size_bytes=size_bytes,
        mime_type=mime,
        password_hash=hash_password(password) if password.strip() else None,
        max_downloads=max_d_int,
        download_count=0,
        published=(published == "on"),
    )
    session.add(obj)
    await session.commit()
    return RedirectResponse("/admin/documents", status_code=303)


@router.post("/documents/{did}/toggle")
async def documents_toggle(
    request: Request, did: int, session: AsyncSession = Depends(get_session)
):
    if not current_admin(request):
        return _redirect_login()
    obj = await session.get(models.Document, did)
    if obj is not None:
        obj.published = not obj.published
        await session.commit()
    return RedirectResponse("/admin/documents", status_code=303)


@router.post("/documents/{did}/delete")
async def documents_delete(request: Request, did: int, session: AsyncSession = Depends(get_session)):
    if not current_admin(request):
        return _redirect_login()
    obj = await session.get(models.Document, did)
    if obj is not None:
        # Best-effort delete the underlying file too.
        try:
            from ..config import UPLOADS_DIR

            if obj.file_url:
                fname = obj.file_url.rsplit("/", 1)[-1]
                p = UPLOADS_DIR / fname
                if p.is_file():
                    p.unlink()
        except Exception:  # noqa: BLE001
            pass
        await session.delete(obj)
        await session.commit()
    return RedirectResponse("/admin/documents", status_code=303)


# ----------------- Settings -----------------

@router.get("/settings", response_class=HTMLResponse)
async def settings_get(request: Request, session: AsyncSession = Depends(get_session)):
    if not current_admin(request):
        return _redirect_login()
    return await _render(
        request, session, "admin/settings.html",
        {
            "site": await get_settings_dict(session),  # canonical RU values
            "site_i18n": await get_settings_all_langs(session),
            "keys": list(DEFAULT_SETTINGS.keys()),
        },
    )


_BOOLEAN_SETTINGS = {"cookie_banner_enabled"}


@router.post("/settings")
async def settings_save(request: Request, session: AsyncSession = Depends(get_session)):
    if not current_admin(request):
        return _redirect_login()
    form = await request.form()
    # 1) Canonical (RU) values + booleans
    for k in DEFAULT_SETTINGS:
        if k in _BOOLEAN_SETTINGS:
            await set_setting(session, k, "1" if k in form else "0")
        elif k in form:
            await set_setting(session, k, str(form[k]))
    # 2) Localized variants (BE / EN). Empty string means "no admin override"
    #    — drop any existing row so the built-in translation can shine through.
    for k in DEFAULT_SETTINGS:
        if k in _BOOLEAN_SETTINGS:
            continue
        for lng in LOCALIZED_LANGS:
            field = f"{k}__{lng}"
            if field not in form:
                continue
            value = str(form[field]).strip()
            if value:
                await set_setting(session, field, value)
            else:
                obj = await session.get(models.Setting, field)
                if obj is not None:
                    await session.delete(obj)
                    await session.commit()
    return RedirectResponse("/admin/settings", status_code=303)


# ----------------- Visual editor -----------------

# Keys that may be overridden via the visual editor. We accept any key on POST
# but cap the length to keep the settings table sane.
_CMS_KEY_RE = re.compile(r"^[a-z][a-z0-9_.]{0,63}$")


@router.get("/edit-homepage", response_class=HTMLResponse)
async def edit_homepage(request: Request, session: AsyncSession = Depends(get_session)):
    if not current_admin(request):
        return _redirect_login()
    from ..i18n import pick_language
    from .site import homepage_context
    ctx = await homepage_context(session)
    ctx["cms_edit"] = True
    ctx["lang"] = pick_language(request)
    return templates.TemplateResponse(request, "index.html", ctx)


@router.post("/api/cms")
async def api_cms_save(request: Request, session: AsyncSession = Depends(get_session)):
    if not current_admin(request):
        return JSONResponse({"ok": False, "error": "auth"}, status_code=401)
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "invalid_json"}, status_code=400)
    if not isinstance(payload, dict):
        return JSONResponse({"ok": False, "error": "invalid_payload"}, status_code=400)
    saved = 0
    for key, value in payload.items():
        if not isinstance(key, str) or not _CMS_KEY_RE.match(key):
            continue
        if not isinstance(value, str):
            continue
        # Cap individual values to ~32KB to keep the row reasonable.
        if len(value) > 32_000:
            value = value[:32_000]
        await set_setting(session, f"cms_{key}", value)
        saved += 1
    return {"ok": True, "saved": saved}


@router.post("/api/cms/reset")
async def api_cms_reset(request: Request, session: AsyncSession = Depends(get_session)):
    """Delete all cms_* overrides — restores defaults from the template."""
    if not current_admin(request):
        return JSONResponse({"ok": False, "error": "auth"}, status_code=401)
    rows = (
        await session.execute(
            select(models.Setting).where(models.Setting.key.like("cms_%"))
        )
    ).scalars().all()
    for r in rows:
        await session.delete(r)
    await session.commit()
    return {"ok": True, "removed": len(rows)}


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
