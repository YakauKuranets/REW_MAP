"""Маршруты для агрегированных уведомлений."""

from __future__ import annotations

from compat_flask import jsonify

from . import bp
from ..helpers import require_admin
from ..services.notifications_service import get_notification_counters


@bp.get("/counters")
def api_get_counters():
    """Вернуть агрегированные счётчики уведомлений для администратора.

    Ответ JSON:

    .. code-block:: json

        {
          "requests": 3,
          "pending": 3,
          "chat_unread": 5,
          "total": 8
        }
    """
    require_admin("viewer")
    data = get_notification_counters()
    return jsonify(data)