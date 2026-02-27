from __future__ import annotations

import socket
from typing import Any


class MQTTBrokerCheck:
    """Проверка доступности MQTT брокера (без аутентификации/брутфорса)."""

    def check(self, host: str, port: int = 1883, timeout: float = 1.0) -> dict[str, Any]:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            sock.connect((host, int(port)))
            return {"host": host, "port": port, "reachable": True}
        except Exception:
            return {"host": host, "port": port, "reachable": False}
        finally:
            try:
                sock.close()
            except Exception:
                pass
