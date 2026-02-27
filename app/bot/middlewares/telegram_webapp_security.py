"""Backend security middleware for Telegram Mini App initData validation."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any, Optional
from urllib.parse import parse_qsl

from compat_flask import Response, current_app, g, jsonify, request


def validate_telegram_init_data(init_data: str, bot_token: str) -> bool:
    """Validate Telegram WebApp initData signature using official algorithm."""
    if not init_data or not bot_token:
        return False

    items = dict(parse_qsl(init_data, keep_blank_values=True))
    got_hash = (items.pop("hash", "") or "").strip()
    if not got_hash:
        return False

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(items.items(), key=lambda kv: kv[0]))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    calc_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(calc_hash, got_hash)


def _extract_init_data() -> str:
    """Extract initData from header, JSON body, or query string."""
    header_value = (request.headers.get("X-Telegram-Init-Data") or "").strip()
    if header_value:
        return header_value

    payload: dict[str, Any] = request.get_json(silent=True) or {}
    body_value = str(payload.get("initData") or "").strip()
    if body_value:
        return body_value

    return (request.args.get("initData") or "").strip()


def enforce_telegram_init_data() -> Optional[Response]:
    """Middleware guard: allow only requests with valid Telegram initData."""
    init_data = _extract_init_data()
    bot_token = (current_app.config.get("TELEGRAM_BOT_TOKEN") or "").strip()
    if not validate_telegram_init_data(init_data, bot_token):
        return jsonify({"error": "forbidden"}), 403

    g.telegram_init_data = init_data
    items = dict(parse_qsl(init_data, keep_blank_values=True))
    user_data = {}
    try:
        user_data = json.loads(items.get("user") or "{}")
    except Exception:
        user_data = {}
    g.telegram_webapp_user = user_data if isinstance(user_data, dict) else {}
    return None
