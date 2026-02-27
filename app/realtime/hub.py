"""Realtime hub for ASGI WebSocket clients.

Когда приложение запускается через ASGI (uvicorn/hypercorn) и используется
`asgi_realtime.py`, WebSocket соединения обслуживаются в одном event-loop.

Flask-обработчики (WSGI слой) остаются синхронными, поэтому для рассылки
событий из них используем `asyncio.run_coroutine_threadsafe` в loop ASGI.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, Set


# Важно: тип не импортируем жёстко, чтобы не требовать starlette при WSGI-запуске.
AsgiWebSocket = Any


_clients: Set[AsgiWebSocket] = set()
_asgi_loop: asyncio.AbstractEventLoop | None = None

# Диагностика: простой счётчик подключений.
# Это удобнее, чем читать len(_clients) из WSGI-потока.
_client_count: int = 0


async def register(ws: AsgiWebSocket) -> None:
    global _asgi_loop, _client_count
    if _asgi_loop is None:
        _asgi_loop = asyncio.get_running_loop()
    _clients.add(ws)
    _client_count = len(_clients)


async def unregister(ws: AsgiWebSocket) -> None:
    global _client_count
    _clients.discard(ws)
    _client_count = len(_clients)


def get_stats() -> Dict[str, Any]:
    """Снимок состояния realtime-хаба (для админ-диагностики)."""
    return {
        "ws_clients": int(_client_count),
        "asgi_loop": bool(_asgi_loop is not None),
    }


async def _broadcast(event: str, data: Dict[str, Any]) -> None:
    if not _clients:
        return
    msg = json.dumps({"event": event, "data": data}, ensure_ascii=False)
    dead = set()
    for ws in list(_clients):
        try:
            # starlette.WebSocket: send_text
            await ws.send_text(msg)
        except Exception:
            dead.add(ws)
    for ws in dead:
        _clients.discard(ws)



async def broadcast(event: str, data: Dict[str, Any]) -> None:
    """Асинхронная рассылка (вызывается из event-loop)."""
    await _broadcast(event, data)

def broadcast_sync(event: str, data: Dict[str, Any]) -> None:
    """Синхронная отправка в ASGI WebSocket клиенты (если ASGI loop активен)."""
    if _asgi_loop is None:
        return
    try:
        asyncio.run_coroutine_threadsafe(_broadcast(event, data), _asgi_loop)
    except Exception:
        # не валим основной поток из-за realtime
        return
