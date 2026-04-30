"""Telegram Mini App init-data verification.

Spec: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

# Reject init_data older than this (seconds). Telegram's recommendation is ~24h
# but tighter is better for an admin panel.
MAX_AGE_SECONDS = 60 * 60 * 24


def parse_and_verify_init_data(
    init_data: str,
    bot_token: str,
    *,
    max_age: int = MAX_AGE_SECONDS,
) -> dict | None:
    """Parse Telegram WebApp initData, verify HMAC, return dict with parsed
    fields (including `user` decoded from JSON). Returns None if signature
    fails or required pieces are missing/expired.
    """
    if not init_data or not bot_token:
        return None

    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        return None

    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(pairs.items(), key=lambda kv: kv[0])
    )

    secret_key = hmac.new(
        b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256
    ).digest()
    expected = hmac.new(
        secret_key, data_check_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected, received_hash):
        return None

    # Optional freshness check
    auth_date_raw = pairs.get("auth_date", "")
    try:
        auth_date = int(auth_date_raw)
    except ValueError:
        return None
    if time.time() - auth_date > max_age:
        return None

    # Decode user JSON if present
    user_raw = pairs.get("user")
    user: dict | None = None
    if user_raw:
        try:
            user = json.loads(user_raw)
        except json.JSONDecodeError:
            return None

    return {
        **pairs,
        "user": user,
        "auth_date": auth_date,
    }
