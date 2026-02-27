# -*- coding: utf-8 -*-
"""Модели для аутентификации и управления доступом."""

from __future__ import annotations

from datetime import datetime, timedelta
import secrets

from app.extensions import db


class User(db.Model):
    """Пользователь системы (администратор, оператор)."""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(50), default="operator")
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)

    api_keys = db.relationship("ApiKey", back_populates="user", lazy="selectin")

    def set_password(self, password: str) -> None:
        """Устанавливает хеш пароля."""
        from werkzeug.security import generate_password_hash

        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Проверяет пароль."""
        from werkzeug.security import check_password_hash

        return check_password_hash(self.password_hash, password)

    def __repr__(self) -> str:
        return f"<User {self.username}>"


class ApiKey(db.Model):
    """API-ключи для мобильных клиентов и внешних сервисов."""

    __tablename__ = "api_keys"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(64), unique=True, nullable=False, index=True)
    name = db.Column(db.String(100))
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    permissions = db.Column(db.String(255), default="diagnostics:read")
    last_used = db.Column(db.DateTime)
    expires_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)

    user = db.relationship("User", back_populates="api_keys")

    @staticmethod
    def generate_key() -> str:
        """Генерирует новый API-ключ."""
        return secrets.token_urlsafe(48)[:64]

    @classmethod
    def default_expiry(cls, days: int = 365) -> datetime:
        return datetime.utcnow() + timedelta(days=days)

    def is_valid(self) -> bool:
        """Проверяет, действителен ли ключ."""
        return self.is_active and (self.expires_at is None or self.expires_at > datetime.utcnow())

    def __repr__(self) -> str:
        return f"<ApiKey {self.name} ({self.key[:8]}...)>"
