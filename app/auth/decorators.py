# -*- coding: utf-8 -*-
"""Декораторы для проверки аутентификации (JWT или API-ключ)."""

from __future__ import annotations

from functools import wraps

from compat_flask import current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

from app.extensions import db
from .models import ApiKey


def _touch_last_used(key: ApiKey) -> None:
    key.last_used = db.func.now()
    db.session.add(key)
    db.session.commit()


def api_key_required(view):
    """Проверяет наличие валидного API-ключа в заголовке X-API-Key."""

    @wraps(view)
    def decorated_function(*args, **kwargs):
        header = current_app.config.get("API_KEY_HEADER", "X-API-Key")
        raw_key = (request.headers.get(header) or "").strip()
        if not raw_key:
            return jsonify({"error": "API key missing"}), 401

        key = ApiKey.query.filter_by(key=raw_key).first()
        if not key or not key.is_valid():
            return jsonify({"error": "Invalid or expired API key"}), 401

        _touch_last_used(key)
        request.api_key = key  # type: ignore[attr-defined]
        request.auth_method = "api_key"  # type: ignore[attr-defined]
        return view(*args, **kwargs)

    return decorated_function


def jwt_or_api_required(view):
    """Принимает либо JWT Bearer токен, либо API-ключ."""

    @wraps(view)
    def decorated_function(*args, **kwargs):
        header = current_app.config.get("API_KEY_HEADER", "X-API-Key")
        raw_key = (request.headers.get(header) or "").strip()
        if raw_key:
            key = ApiKey.query.filter_by(key=raw_key).first()
            if key and key.is_valid():
                _touch_last_used(key)
                request.auth_method = "api_key"  # type: ignore[attr-defined]
                request.api_key = key  # type: ignore[attr-defined]
                return view(*args, **kwargs)

        try:
            verify_jwt_in_request()
            request.auth_method = "jwt"  # type: ignore[attr-defined]
            request.jwt_identity = get_jwt_identity()  # type: ignore[attr-defined]
            return view(*args, **kwargs)
        except Exception:
            return jsonify({"error": "Authentication required"}), 401

    return decorated_function


def require_audit_auth(view):
    """Backward-compatible alias for audit endpoints."""

    return jwt_or_api_required(view)
