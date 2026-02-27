"""Blueprint realtime.

Маршруты:

- ``GET /api/realtime/token`` — выдать токен для подключения к WebSocket (через Rust gateway).

Токен выдаётся только администратору (require_admin).
"""

from compat_flask import Blueprint


bp = Blueprint("realtime", __name__, url_prefix="/api/realtime")


def send_alert_to_dashboard(alert_data: dict) -> None:
    """Отправить событие алерта во все realtime-клиенты панели."""
    from app.sockets import broadcast_event_sync

    broadcast_event_sync("alert", alert_data)


from . import routes  # noqa: E402,F401
