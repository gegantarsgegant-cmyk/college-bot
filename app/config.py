from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
UPLOADS_DIR = STATIC_DIR / "uploads"
DATA_DIR = PROJECT_DIR / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    PUBLIC_URL: str = "http://localhost:8000"
    # Optional override URL for links sent inside Telegram (used when the
    # tunnel that hosts PUBLIC_URL requires HTTP basic auth that has to be
    # embedded in the URL like https://user:pass@host). If empty, PUBLIC_URL
    # is used as-is.
    BOT_PUBLIC_URL: str = ""
    SECRET_KEY: str = "dev-only-not-for-production"

    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin"

    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_ADMIN_IDS: str = ""
    TELEGRAM_NOTIFY_CHAT_ID: str = ""

    BOT_MODE: str = "polling"  # "polling" or "webhook"
    WEBHOOK_BASE_URL: str = ""
    WEBHOOK_SECRET: str = ""

    DATABASE_URL: str = "sqlite+aiosqlite:///./data/college.db"

    @property
    def admin_ids(self) -> set[int]:
        out: set[int] = set()
        for chunk in self.TELEGRAM_ADMIN_IDS.replace(";", ",").split(","):
            chunk = chunk.strip()
            if chunk and chunk.lstrip("-").isdigit():
                out.add(int(chunk))
        return out

    @property
    def bot_enabled(self) -> bool:
        return bool(self.TELEGRAM_BOT_TOKEN)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
