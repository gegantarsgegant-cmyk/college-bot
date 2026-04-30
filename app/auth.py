"""Admin web auth: signed cookie sessions via itsdangerous."""

from __future__ import annotations

import time

from fastapi import Request
from itsdangerous import BadSignature, URLSafeTimedSerializer

from .config import settings

SESSION_COOKIE = "college_admin"
SESSION_MAX_AGE = 60 * 60 * 24 * 7  # 7 days

_serializer = URLSafeTimedSerializer(settings.SECRET_KEY, salt="admin-session")


def make_session_token(user_id: int, username: str) -> str:
    return _serializer.dumps({"uid": user_id, "u": username, "t": int(time.time())})


def read_session_token(token: str) -> dict | None:
    try:
        return _serializer.loads(token, max_age=SESSION_MAX_AGE)
    except BadSignature:
        return None


def current_admin(request: Request) -> dict | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    return read_session_token(token)


def require_admin(request: Request) -> dict | None:
    """Return admin dict or None — caller decides what to do (redirect/401)."""
    return current_admin(request)
