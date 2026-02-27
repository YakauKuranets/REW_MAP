"""
Пакет аутентификации и управления ролью пользователя.

Blueprint auth_bp определяет маршруты для установки роли и
авторизации администратора. Сессия используется для хранения
информации о текущей роли.
"""

from compat_flask import Blueprint

bp = Blueprint('auth', __name__)

from . import routes  # noqa: F401

from . import models  # noqa: F401
