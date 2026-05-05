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
    # Two-line navbar logo. Top line is small/uppercase, main is the brand.
    "nav_logo_top": "ХДН",
    "nav_logo_main": "Библейский Колледж",
    # Footer brand block. Allow <br> for line breaks.
    "footer_logo": "Библейский<br>Колледж ХВЕ",
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
    # Cookie / consent banner shown on first visit. Disabled by default.
    "cookie_banner_enabled": "0",
    "cookie_banner_text": (
        "Мы используем файлы cookie для корректной работы сайта и улучшения "
        "пользовательского опыта. Продолжая пользоваться сайтом, вы "
        "соглашаетесь с этим, а также с пользовательским соглашением."
    ),
    "cookie_banner_terms_url": "",
    "cookie_banner_button_text": "Принимаю",
    # ----- Donations -----
    "donate_eyebrow": "Поддержать колледж",
    "donate_title": "Ваше пожертвование — это служение",
    "donate_lead": (
        "Каждое пожертвование помогает нам обучать новых служителей, "
        "поддерживать преподавателей и развивать программы Библейского колледжа. "
        "Спасибо, что вы с нами."
    ),
    "donate_erip_path": "Образование и развитие → Высшее, среднее → Библейский Колледж ХДН",
    "donate_erip_code": "уточните в банке",
    "donate_bank_name": "ОАО «Беларусбанк», г. Минск",
    "donate_bank_iban": "BY00 AKBB 0000 0000 0000 0000 0000",
    "donate_bank_bic": "AKBBBY2X",
    "donate_bank_recipient": "ХДН «Библейский Колледж»",
    "donate_bank_unp": "100000000",
    "donate_card_url": "",
    "donate_thank_you": "Да благословит вас Господь!",
    # Per-method enable toggles ('1' = visible on /donate, '0' = hidden).
    "donate_method_erip_enabled": "1",
    "donate_method_card_enabled": "1",
    "donate_method_bank_enabled": "1",
    "donate_method_cash_enabled": "1",
    "donate_method_crypto_enabled": "0",
    # Crypto wallets — multiple USDT networks + BTC.
    # Per-network enable flag determines whether the network shows in the
    # USDT switcher; if all USDT networks are off the USDT block is hidden.
    "donate_crypto_usdt_trc20": "",
    "donate_crypto_usdt_trc20_enabled": "1",
    "donate_crypto_usdt_bsc": "",
    "donate_crypto_usdt_bsc_enabled": "1",
    "donate_crypto_usdt_sol": "",
    "donate_crypto_usdt_sol_enabled": "0",
    "donate_crypto_usdt_ton": "",
    "donate_crypto_usdt_ton_enabled": "0",
    "donate_crypto_btc": "",
    "donate_crypto_btc_enabled": "1",
    "donate_crypto_eth": "",
    "donate_crypto_eth_enabled": "0",
}


# Pre-seeded BE / EN translations of the default Russian settings. Admins can
# override any of these in /admin/settings; we just ship sensible defaults so
# the public site looks complete in all three languages out of the box.
DEFAULT_SETTINGS_I18N: dict[str, dict[str, str]] = {
    "be": {
        "site_title": "Біблейскі Каледж ХВЕ",
        "hero_eyebrow": "Духоўная навучальная ўстанова · Мінск, Беларусь",
        "hero_subtitle": "Бог шукае лідараў будучых пераменаў",
        "nav_logo_top": "ХДН",  # Хрыстос Для Народаў — та ж абрэвіятура, што і па-руску
        "nav_logo_main": "Біблейскі Каледж",
        "footer_logo": "Біблейскі<br>Каледж ХВЕ",
        "contact_address": "220092, г. Мінск, вул. Бельскага, 15, оф. 103\nпоруч са ст. м. «Спартыўная»",
        "contact_email": "cfnbel@gmail.com — прыёмная камісія\nadmin@biblecollege.by — адміністратар",
        "contact_phones": "+375 17 393 53 94\n+375 29 602 32 32\n+375 33 660 32 32",
        "contact_hours": "Панядзелак — пятніца\n10:00 – 18:00",
        "cookie_banner_text": (
            "Мы выкарыстоўваем файлы cookie для карэктнай работы сайта і "
            "паляпшэння карыстальніцкага вопыту. Працягваючы карыстацца "
            "сайтам, вы згаджаецеся з гэтым, а таксама з карыстальніцкай "
            "пагадненнем."
        ),
        "cookie_banner_button_text": "Прымаю",
        "donate_eyebrow": "Падтрымаць каледж",
        "donate_title": "Ваша ахвяраванне — гэта служэнне",
        "donate_lead": (
            "Кожнае ахвяраванне дапамагае нам навучаць новых служыцеляў, "
            "падтрымліваць выкладчыкаў і развіваць праграмы Біблейскага каледжа. "
            "Дзякуй, што вы з намі."
        ),
        "donate_erip_path": "Адукацыя і развіццё → Вышэйшая, сярэдняя → Біблейскі Каледж ХДН",
        "donate_bank_name": "ААТ «Беларусбанк», г. Мінск",
        "donate_bank_recipient": "ХДН «Біблейскі Каледж»",
        "donate_thank_you": "Хай дабраславіць вас Гасподзь!",
    },
    "en": {
        "site_title": "Bible College of CFEF",
        "hero_eyebrow": "Theological educational institution · Minsk, Belarus",
        "hero_subtitle": "God is looking for leaders of tomorrow's change",
        "nav_logo_top": "CFN",  # Christ for the Nations
        "nav_logo_main": "Bible College",
        "footer_logo": "Bible<br>College of CFEF",
        "contact_address": "220092, Minsk, Belskogo str. 15, office 103\nnext to «Sportivnaya» metro station",
        "contact_email": "cfnbel@gmail.com — admissions office\nadmin@biblecollege.by — administrator",
        "contact_phones": "+375 17 393 53 94\n+375 29 602 32 32\n+375 33 660 32 32",
        "contact_hours": "Monday – Friday\n10:00 – 18:00",
        "cookie_banner_text": (
            "We use cookies to make the site work correctly and to improve "
            "your experience. By continuing to use this site you agree to "
            "our cookie policy and terms of use."
        ),
        "cookie_banner_button_text": "I agree",
        "donate_eyebrow": "Support the college",
        "donate_title": "Your gift is a ministry",
        "donate_lead": (
            "Every gift helps us train new ministers, support our faculty, "
            "and grow the programs of the Bible College. Thank you for "
            "standing with us."
        ),
        "donate_erip_path": "Education and development → Higher, secondary → Bible College CFEF",
        "donate_bank_name": "JSC «Belarusbank», Minsk",
        "donate_bank_recipient": "CFEF «Bible College»",
        "donate_thank_you": "May the Lord bless you!",
    },
}


# Languages with per-language overrides for settings. Convention: stored as
# `<base_key>__<lang>` in the Setting table (double-underscore is not used by
# any base key). The base key is the Russian default. When rendering the site
# in BE/EN, we look up the localized variant first; if it's missing or blank
# we fall back to the base (RU) value so nothing ever "breaks".
LOCALIZED_LANGS: tuple[str, ...] = ("be", "en")


async def get_settings_dict(
    session: AsyncSession, lang: str = "ru"
) -> dict[str, str]:
    """Return all settings as a dict (localized to ``lang``), with defaults filled in.

    Resolution order for each key:
      1. ``<key>__<lang>`` row in the DB (admin-edited override)
      2. ``<key>`` row in the DB (canonical RU value, possibly admin-edited)
      3. Built-in BE/EN translation from ``DEFAULT_SETTINGS_I18N`` (only if lang != ru)
      4. Built-in RU default from ``DEFAULT_SETTINGS``
    """
    rows = (await session.execute(select(models.Setting))).scalars().all()
    out = dict(DEFAULT_SETTINGS)
    if lang in DEFAULT_SETTINGS_I18N:
        out.update(DEFAULT_SETTINGS_I18N[lang])
    overrides: dict[str, str] = {}
    for r in rows:
        if "__" in r.key:
            base, _, suffix = r.key.partition("__")
            if suffix == lang and (r.value or "").strip():
                overrides[base] = r.value
            continue
        # Canonical RU row from the DB. If the admin edited the RU value but
        # left BE/EN blank, this row should NOT silently overwrite our
        # built-in BE/EN translation; it only takes effect when lang == 'ru'
        # OR when no built-in translation exists for that key.
        if lang == "ru" or r.key not in DEFAULT_SETTINGS_I18N.get(lang, {}):
            out[r.key] = r.value
    out.update(overrides)
    return out


async def get_settings_all_langs(
    session: AsyncSession,
) -> dict[str, dict[str, str]]:
    """Return settings as ``{base_key: {"ru": ..., "be": ..., "en": ...}}``
    for use by the admin UI when rendering language tabs. Built-in BE/EN
    translations show through as the default placeholder so the admin can
    see what the public site is currently using.
    """
    rows = (await session.execute(select(models.Setting))).scalars().all()
    by_key: dict[str, dict[str, str]] = {}
    for k, v in DEFAULT_SETTINGS.items():
        entry = {"ru": v}
        for lng in LOCALIZED_LANGS:
            entry[lng] = DEFAULT_SETTINGS_I18N.get(lng, {}).get(k, "")
        by_key[k] = entry
    for r in rows:
        if "__" in r.key:
            base, _, suffix = r.key.partition("__")
            if suffix in LOCALIZED_LANGS:
                by_key.setdefault(
                    base,
                    {"ru": "", **{lng: DEFAULT_SETTINGS_I18N.get(lng, {}).get(base, "") for lng in LOCALIZED_LANGS}},
                )
                # Empty admin row means "no override" — show empty input,
                # let the placeholder/built-in default fall through.
                by_key[base][suffix] = r.value
            continue
        by_key.setdefault(r.key, {"ru": "", **{lng: "" for lng in LOCALIZED_LANGS}})
        by_key[r.key]["ru"] = r.value
    return by_key


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


async def ensure_default_programs(session: AsyncSession) -> None:
    """Seed the 3 default programs (music/theology/theatre) on first run."""
    existing = (
        await session.execute(select(models.Program.id).limit(1))
    ).scalar_one_or_none()
    if existing is not None:
        return
    from .seed_programs import DEFAULT_PROGRAMS

    for i, p in enumerate(DEFAULT_PROGRAMS):
        prog = models.Program(
            slug=p["slug"],
            number=p.get("number", ""),
            tag=p.get("tag", ""),
            title=p["title"],
            description=p.get("description", ""),
            form_label=p.get("form_label", ""),
            term_label=p.get("term_label", ""),
            degree_label=p.get("degree_label", ""),
            tuition_amount=p.get("tuition_amount", ""),
            tuition_note=p.get("tuition_note", ""),
            documents=p.get("documents", []),
            sort_order=i,
            published=True,
        )
        session.add(prog)
        await session.flush()  # get prog.id
        for j, s in enumerate(p.get("specialties", [])):
            session.add(
                models.ProgramSpecialty(
                    program_id=prog.id,
                    num=s.get("num", ""),
                    name=s["name"],
                    subs=s.get("subs", ""),
                    qualification=s.get("qualification", ""),
                    sort_order=j,
                )
            )
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


async def backfill_teachers_i18n(session: AsyncSession) -> None:
    """For every teacher, fill missing BE/EN entries in the i18n column using
    ``app.i18n_seed`` translation tables. Existing per-language values are
    left intact so admin edits are never overwritten.
    """
    from .i18n_seed import translate_name, translate_role, translate_subjects

    rows = (await session.execute(select(models.Teacher))).scalars().all()
    changed = 0
    for t in rows:
        i18n = dict(t.i18n or {})
        for lang in ("be", "en"):
            bucket = dict(i18n.get(lang) or {})
            if not bucket.get("name"):
                bucket["name"] = translate_name(t.name or "", lang)
            if not bucket.get("role"):
                bucket["role"] = translate_role(t.role or "", lang)
            if not bucket.get("subjects"):
                bucket["subjects"] = translate_subjects(t.subjects or [], lang)
            # drop empty fields so fallback logic still kicks in
            bucket = {k: v for k, v in bucket.items() if v}
            if bucket:
                i18n[lang] = bucket
        if i18n != (t.i18n or {}):
            t.i18n = i18n
            changed += 1
    if changed:
        await session.commit()


async def backfill_programs_i18n(session: AsyncSession) -> None:
    """For each program with a known slug (music / theology / theatre), fill
    any missing BE/EN field with the seed value. Admin overrides are
    preserved — only empty fields are populated.
    """
    from .i18n_seed import program_seed

    rows = (await session.execute(select(models.Program))).scalars().all()
    changed = 0
    for p in rows:
        i18n = dict(p.i18n or {})
        for lang in ("be", "en"):
            seed = program_seed(p.slug or "", lang)
            if not seed:
                continue
            bucket = dict(i18n.get(lang) or {})
            for k, v in seed.items():
                if not bucket.get(k):
                    bucket[k] = v
            bucket = {k: v for k, v in bucket.items() if v}
            if bucket:
                i18n[lang] = bucket
        if i18n != (p.i18n or {}):
            p.i18n = i18n
            changed += 1
    if changed:
        await session.commit()


# ---------------- Applications ----------------

def _new_history_event(kind: str, text: str = "", who: str = "system") -> dict[str, Any]:
    return {
        "ts": datetime.utcnow().isoformat(timespec="seconds"),
        "who": who,
        "kind": kind,  # created | status | note | contact | tag | assign
        "text": text,
    }


async def create_application(session: AsyncSession, data: dict[str, Any]) -> models.Application:
    obj = models.Application(
        name=(data.get("name") or "").strip()[:120],
        lastname=(data.get("lastname") or "").strip()[:120],
        phone=(data.get("phone") or "").strip()[:120],
        program=(data.get("program") or "").strip()[:64],
        church=(data.get("church") or "").strip()[:255],
        note=(data.get("note") or "").strip(),
        tags=[],
        history=[_new_history_event("created", "Заявка получена с сайта")],
    )
    session.add(obj)
    await session.commit()
    await session.refresh(obj)
    return obj


async def list_applications(
    session: AsyncSession,
    *,
    status: str | None = None,
    program: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    search: str | None = None,
    limit: int = 500,
) -> list[models.Application]:
    stmt = select(models.Application).order_by(models.Application.created_at.desc()).limit(limit)
    if status:
        stmt = stmt.where(models.Application.status == status)
    if program:
        stmt = stmt.where(models.Application.program == program)
    if date_from:
        stmt = stmt.where(models.Application.created_at >= date_from)
    if date_to:
        stmt = stmt.where(models.Application.created_at <= date_to)
    if search:
        from sqlalchemy import or_

        like = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                models.Application.name.ilike(like),
                models.Application.lastname.ilike(like),
                models.Application.phone.ilike(like),
                models.Application.church.ilike(like),
            )
        )
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


def _append_history(obj: models.Application, event: dict[str, Any]) -> None:
    """Append an event to the application's history JSON list (in place)."""
    h = list(obj.history or [])
    h.append(event)
    obj.history = h


async def update_application_status(
    session: AsyncSession,
    app_id: int,
    status: str,
    admin_comment: str = "",
    who: str = "admin",
) -> models.Application | None:
    obj = await session.get(models.Application, app_id)
    if obj is None:
        return None
    if obj.status != status:
        from .models import STATUS_LABELS

        prev_lbl = STATUS_LABELS.get(obj.status, obj.status)
        new_lbl = STATUS_LABELS.get(status, status)
        _append_history(
            obj,
            _new_history_event(
                "status", f"{prev_lbl} → {new_lbl}", who=who
            ),
        )
        obj.status = status
        # When the admin marks the application as 'contacted' we log this as
        # the most recent contact moment so the stale-reminder skips it.
        if status in {"contacted", "docs_submitted"}:
            obj.last_contacted_at = datetime.utcnow()
    if admin_comment:
        obj.admin_comment = admin_comment
    await session.commit()
    await session.refresh(obj)
    return obj


async def add_application_note(
    session: AsyncSession, app_id: int, text: str, who: str = "admin"
) -> models.Application | None:
    obj = await session.get(models.Application, app_id)
    if obj is None or not text.strip():
        return obj
    _append_history(obj, _new_history_event("note", text.strip()[:2000], who=who))
    await session.commit()
    await session.refresh(obj)
    return obj


async def mark_application_contacted(
    session: AsyncSession, app_id: int, who: str = "admin"
) -> models.Application | None:
    obj = await session.get(models.Application, app_id)
    if obj is None:
        return None
    obj.last_contacted_at = datetime.utcnow()
    _append_history(obj, _new_history_event("contact", "Связались с абитуриентом", who=who))
    await session.commit()
    await session.refresh(obj)
    return obj


async def update_application_tags(
    session: AsyncSession, app_id: int, tags: list[str], who: str = "admin"
) -> models.Application | None:
    obj = await session.get(models.Application, app_id)
    if obj is None:
        return None
    cleaned = [t.strip()[:32] for t in tags if t and t.strip()]
    cleaned = list(dict.fromkeys(cleaned))[:12]
    if list(obj.tags or []) != cleaned:
        obj.tags = cleaned
        _append_history(
            obj,
            _new_history_event("tag", "Теги: " + (", ".join(cleaned) or "—"), who=who),
        )
    await session.commit()
    await session.refresh(obj)
    return obj


async def assign_application(
    session: AsyncSession, app_id: int, assigned_to: str, who: str = "admin"
) -> models.Application | None:
    obj = await session.get(models.Application, app_id)
    if obj is None:
        return None
    name = (assigned_to or "").strip()[:120]
    if obj.assigned_to != name:
        obj.assigned_to = name
        _append_history(
            obj,
            _new_history_event("assign", f"Ответственный: {name or '—'}", who=who),
        )
    await session.commit()
    await session.refresh(obj)
    return obj


async def stale_applications(
    session: AsyncSession, *, days: int = 3
) -> list[models.Application]:
    """Applications that haven't moved past 'new'/'contacted' for `days` days."""
    from datetime import timedelta

    cutoff = datetime.utcnow() - timedelta(days=days)
    stmt = (
        select(models.Application)
        .where(models.Application.status.in_(["new", "contacted"]))
        .where(models.Application.created_at <= cutoff)
        .order_by(models.Application.created_at.asc())
    )
    rows = list((await session.execute(stmt)).scalars().all())
    # Filter further: skip if last_contacted_at is recent, or last_reminder_at < 24h ago.
    out: list[models.Application] = []
    now = datetime.utcnow()
    for r in rows:
        if r.last_contacted_at and r.last_contacted_at >= cutoff:
            continue
        if r.last_reminder_at and (now - r.last_reminder_at) < timedelta(hours=20):
            continue
        out.append(r)
    return out


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
