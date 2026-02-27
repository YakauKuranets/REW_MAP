"""Helpers for token and API-key auth."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from flask import current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash

from .models import ApiKey


def _serializer() -> URLSafeTimedSerializer:
    secret = current_app.config.get("JWT_SECRET_KEY") or current_app.config.get("SECRET_KEY")
    return URLSafeTimedSerializer(secret_key=secret, salt="auth-jwt")


def create_access_token(identity: str, role: str) -> str:
    payload = {
        "sub": identity,
        "role": role,
        "typ": "access",
        "iat": int(datetime.now(timezone.utc).timestamp()),
    }
    return _serializer().dumps(payload)


def verify_access_token(token: str) -> Optional[Dict[str, Any]]:
    max_age = int(current_app.config.get("JWT_ACCESS_TOKEN_EXPIRES", timedelta(hours=1)).total_seconds())
    try:
        data = _serializer().loads(token, max_age=max_age)
        if data.get("typ") != "access":
            return None
        return data
    except (BadSignature, SignatureExpired):
        return None


def generate_api_key() -> str:
    return ApiKey.generate_key()


def authenticate_api_key(raw_key: str) -> Optional[ApiKey]:
    if not raw_key:
        return None

    # Primary path: plain key model.
    item = ApiKey.query.filter_by(key=raw_key, is_active=True).first()
    if item and item.is_valid():
        item.last_used = datetime.utcnow()
        from app.extensions import db

        db.session.add(item)
        db.session.commit()
        return item

    # Backward compatibility with previous hashed schema, if present.
    prefix = raw_key[:8]
    candidates = ApiKey.query.filter_by(is_active=True).all()
    for key in candidates:
        key_prefix = getattr(key, "key_prefix", None)
        key_hash = getattr(key, "key_hash", None)
        if key_prefix != prefix or not key_hash:
            continue
        if check_password_hash(key_hash, raw_key):
            key.last_used = datetime.utcnow()
            from app.extensions import db

            db.session.add(key)
            db.session.commit()
            return key
    return None
