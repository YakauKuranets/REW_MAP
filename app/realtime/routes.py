"""HTTP endpoints for realtime tokens."""

from __future__ import annotations

from compat_flask import current_app, jsonify, request, session

from . import bp
from .tokens import issue_token
from .hub import get_stats
from ..helpers import require_admin


@bp.get("/token")
def get_realtime_token():
    """Выдать короткоживущий токен для подключения к realtime.

    Возвращает JSON:
      - token
      - expires_in
      - ws_url_sameport (ASGI-режим: /ws на том же порту)
      - ws_url_port (legacy/dev: отдельный WS_PORT)
    """
    require_admin("viewer")

    ttl = int(current_app.config.get("REALTIME_TOKEN_TTL_SEC", 600))
    ws_port = int(current_app.config.get("WS_PORT", 8765))

    username = session.get("admin_username") or session.get("username")
    role = session.get("admin_role") or "viewer"

    payload = {
        "u": username or "admin",
        "r": role,
        "v": 1,
    }
    tok = issue_token(current_app.secret_key, payload)

    # sameport: ws(s)://host[:port]/ws?token=...
    scheme = "wss" if request.is_secure else "ws"
    host = request.host  # включает порт если есть
    ws_url_sameport = f"{scheme}://{host}/ws?token={tok}"

    if str(current_app.config.get('REALTIME_DISABLE_SAMEPORT', '0')).lower() in {'1','true','yes'}:
        ws_url_sameport = None

    # отдельный порт: ws(s)://hostname:WS_PORT/ws?token=...
    hostname = request.host.split(":")[0]
    ws_url_port = f"{scheme}://{hostname}:{ws_port}/ws?token={tok}"

    return jsonify(
        token=tok,
        expires_in=ttl,
        ws_url_sameport=ws_url_sameport,
        ws_url_port=ws_url_port,
    )


@bp.get('/stats')
def realtime_stats():
    """Диагностика realtime (сколько WS клиентов подключено).

    Полезно для стресс-теста 1–2 часа: видно, не отваливаются ли клиенты.
    """
    require_admin('viewer')
    return jsonify(get_stats())
