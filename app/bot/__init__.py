"""
Пакет API для телеграм‑бота.

Bot API позволяет создавать новые заявки без аутентификации
администратора, используя API‑ключ. Заявки записываются в
очередь pending.
"""

from compat_flask import Blueprint

bp = Blueprint('bot', __name__)

from . import routes  # noqa: F401
