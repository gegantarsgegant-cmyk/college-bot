from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


class ApplicationStatus(StrEnum):
    new = "new"
    in_progress = "in_progress"
    accepted = "accepted"
    rejected = "rejected"


class AdminUser(Base):
    __tablename__ = "admin_users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class News(Base):
    __tablename__ = "news"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    published: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)


class Event(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    starts_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    location: Mapped[str] = mapped_column(String(255), default="")
    published: Mapped[bool] = mapped_column(Boolean, default=True)


class Teacher(Base):
    __tablename__ = "teachers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    initials: Mapped[str] = mapped_column(String(8), default="")
    name: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(255), default="")
    bio: Mapped[str] = mapped_column(Text, default="")
    # store list of subjects as JSON array
    subjects: Mapped[list] = mapped_column(JSON, default=list)
    # one or many of: music, theology, theatre, all
    departments: Mapped[list] = mapped_column(JSON, default=list)
    photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, index=True)
    published: Mapped[bool] = mapped_column(Boolean, default=True)


class GalleryItem(Base):
    __tablename__ = "gallery"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), default="")
    image_url: Mapped[str] = mapped_column(String(500))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, index=True)
    published: Mapped[bool] = mapped_column(Boolean, default=True)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    file_url: Mapped[str] = mapped_column(String(500))
    slug: Mapped[str] = mapped_column(String(32), unique=True, index=True, default="")
    original_filename: Mapped[str] = mapped_column(String(500), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    mime_type: Mapped[str] = mapped_column(String(120), default="")
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    max_downloads: Mapped[int | None] = mapped_column(Integer, nullable=True)
    download_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, index=True)
    published: Mapped[bool] = mapped_column(Boolean, default=True)


class Setting(Base):
    """Free-form key/value site settings (contact info, hero copy, etc.)."""

    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


class Application(Base):
    __tablename__ = "applications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    lastname: Mapped[str] = mapped_column(String(120), default="")
    phone: Mapped[str] = mapped_column(String(120), default="")
    program: Mapped[str] = mapped_column(String(64), default="")
    church: Mapped[str] = mapped_column(String(255), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default=ApplicationStatus.new.value, index=True)
    admin_comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    notified_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Program(Base):
    """A study program shown on the homepage and as a sub-page."""

    __tablename__ = "programs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    number: Mapped[str] = mapped_column(String(8), default="")
    tag: Mapped[str] = mapped_column(String(120), default="")
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    form_label: Mapped[str] = mapped_column(String(120), default="")
    term_label: Mapped[str] = mapped_column(String(255), default="")
    degree_label: Mapped[str] = mapped_column(String(255), default="")
    tuition_amount: Mapped[str] = mapped_column(String(64), default="")
    tuition_note: Mapped[str] = mapped_column(String(500), default="")
    documents: Mapped[list] = mapped_column(JSON, default=list)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, index=True)
    published: Mapped[bool] = mapped_column(Boolean, default=True)


class ProgramSpecialty(Base):
    """A specialty / track inside a program (e.g. 'Звукорежиссура')."""

    __tablename__ = "program_specialties"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    program_id: Mapped[int] = mapped_column(Integer, index=True)
    num: Mapped[str] = mapped_column(String(8), default="")
    name: Mapped[str] = mapped_column(String(255))
    subs: Mapped[str] = mapped_column(Text, default="")
    qualification: Mapped[str] = mapped_column(String(500), default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, index=True)


class BotUser(Base):
    """Telegram users who interacted with the bot. Used to broadcast news."""

    __tablename__ = "bot_users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    username: Mapped[str] = mapped_column(String(64), default="")
    first_name: Mapped[str] = mapped_column(String(120), default="")
    last_name: Mapped[str] = mapped_column(String(120), default="")
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


__all__ = [
    "AdminUser",
    "Application",
    "ApplicationStatus",
    "BotUser",
    "Document",
    "Event",
    "GalleryItem",
    "News",
    "Program",
    "ProgramSpecialty",
    "Setting",
    "Teacher",
]
