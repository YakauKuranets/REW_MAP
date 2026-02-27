"""Blueprint уведомлений.

Маршруты:

- ``GET /api/notifications/counters`` — агрегированные счётчики для
  колокольчика и индикатора чата.
"""

from compat_flask import Blueprint

bp = Blueprint("notifications", __name__, url_prefix="/api/notifications")

from . import routes  # noqa: E402,F401
