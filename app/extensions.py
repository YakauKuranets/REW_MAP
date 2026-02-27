"""
Инициализация расширений Flask.

В этом модуле размещаются объекты, которые будут использованы
приложением: например SQLAlchemy. Отделение расширений в
отдельный файл помогает избежать циклических импортов и
облегчает тестирование.
"""

from __future__ import annotations

from celery import Celery
from compat_flask import Flask
from flask_jwt_extended import JWTManager
from flask_sqlalchemy import SQLAlchemy
import redis

from app.utils.env_loader import settings

# Инициализируем объект SQLAlchemy без привязки к конкретному приложению.
# Приложение привязывается в create_app() (см. app/__init__.py).
db = SQLAlchemy()

# Celery-приложение инициализируется через init_celery(app).
celery_app = Celery(__name__)
jwt = JWTManager()
redis_client = redis.from_url(settings.redis_url, decode_responses=True)


def init_celery(app: Flask) -> Celery:
    """Привязать Celery к конфигу Flask-приложения."""
    celery_app.conf.update(
        broker_url=app.config["CELERY_BROKER_URL"],
        result_backend=app.config["CELERY_RESULT_BACKEND"],
        task_ignore_result=True,
        broker_connection_retry_on_startup=True,
        beat_schedule=app.config.get("CELERY_BEAT_SCHEDULE", {}),
        timezone=app.config.get("CELERY_TIMEZONE", "UTC"),
    )

    class FlaskTask(celery_app.Task):
        abstract = True

        def __call__(self, *args, **kwargs):
            with app.app_context():
                return super().__call__(*args, **kwargs)

    celery_app.Task = FlaskTask
    return celery_app


# JWT-like token serializer (itsdangerous).
def init_auth(app: Flask) -> None:
    """Initialize auth token utilities."""
    from itsdangerous import URLSafeTimedSerializer

    secret = app.config.get("JWT_SECRET_KEY") or app.config.get("SECRET_KEY")
    app.extensions["jwt_serializer"] = URLSafeTimedSerializer(secret_key=secret, salt="auth-jwt")


def init_extensions(app: Flask) -> None:
    """Init all Flask extensions in one place."""
    db.init_app(app)
    init_celery(app)
    init_auth(app)
    jwt.init_app(app)
