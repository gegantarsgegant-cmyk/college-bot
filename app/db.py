from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(settings.DATABASE_URL, echo=False, future=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session


async def init_db() -> None:
    # Import models so SQLAlchemy registers them on Base.metadata
    from . import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Lightweight inline migrations for SQLite — add new columns to
        # existing tables when the schema evolved (create_all only creates
        # missing tables, never adds columns).
        await conn.run_sync(_apply_lightweight_migrations)


def _apply_lightweight_migrations(sync_conn) -> None:
    """Add columns added in later releases without losing data.

    Idempotent — safe to run on every startup.
    """
    from sqlalchemy import text

    def _columns(table: str) -> set[str]:
        rows = sync_conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
        return {r[1] for r in rows}

    documents_cols = _columns("documents")
    additions = {
        "slug": "VARCHAR(32) DEFAULT ''",
        "original_filename": "VARCHAR(500) DEFAULT ''",
        "size_bytes": "INTEGER DEFAULT 0",
        "mime_type": "VARCHAR(120) DEFAULT ''",
        "password_hash": "VARCHAR(255)",
        "max_downloads": "INTEGER",
        "download_count": "INTEGER DEFAULT 0",
        "created_at": "DATETIME",
    }
    for col, ddl in additions.items():
        if col not in documents_cols:
            sync_conn.execute(text(f"ALTER TABLE documents ADD COLUMN {col} {ddl}"))
