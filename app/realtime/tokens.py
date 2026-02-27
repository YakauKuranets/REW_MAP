"""Realtime token helpers.

Используем подписанные токены (itsdangerous), чтобы не тащить куки-сессию
в WebSocket-рукопожатие и не открывать WS всем подряд.

Токен выдаётся только администратору через HTTP (`GET /api/realtime/token`).
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from datetime import timedelta
from compat_flask import current_app

from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired


_SALT = "mapv12-realtime"


def _serializer(secret_key: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret_key=secret_key, salt=_SALT)


def issue_token(secret_key: str, payload: Dict[str, Any]) -> str:
    """Выпустить токен (подписанный payload)."""
    return _serializer(secret_key).dumps(payload)


def verify_token(secret_key: str, token: str, *, max_age: int) -> Optional[Dict[str, Any]]:
    """Проверить токен. Возвращает payload или None."""
    try:
        data = _serializer(secret_key).loads(token, max_age=max_age)
        return data if isinstance(data, dict) else None
    except (BadSignature, SignatureExpired):
        return None


def generate_websocket_token(payload: Dict[str, Any], *, expires_delta: Optional[timedelta] = None) -> str:
    """Generate token for WS clients using app secret."""
    secret = current_app.config.get("JWT_SECRET_KEY") or current_app.secret_key
    data = dict(payload or {})
    if expires_delta is not None:
        data["exp_seconds"] = int(expires_delta.total_seconds())
    return issue_token(secret, data)


def verify_websocket_token(token: str, *, max_age: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Verify websocket token against app secret/current config."""
    secret = current_app.config.get("JWT_SECRET_KEY") or current_app.secret_key
    ttl = int(max_age or current_app.config.get("REALTIME_TOKEN_TTL_SEC", 3600))
    return verify_token(secret, token, max_age=ttl)
