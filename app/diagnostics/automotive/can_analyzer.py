# -*- coding: utf-8 -*-
"""
Анализатор CAN-шины для диагностики автомобильных систем.
Собирает статистику трафика и проверяет наличие базовых диагностических признаков.
"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

try:
    import can
except Exception:  # pragma: no cover - optional dependency
    can = None  # type: ignore[assignment]


class CANBusAnalyzer:
    """Пассивный мониторинг и анализ CAN-трафика (без активного воздействия)."""

    def __init__(self, interface: str = "socketcan", channel: str = "can0", bitrate: int = 500000):
        self.interface = interface
        self.channel = channel
        self.bitrate = bitrate
        self.bus: Any = None
        self.running = False
        self.messages: list[dict[str, Any]] = []

    def start_monitoring(self, duration: int = 10) -> bool:
        """Запускает сбор CAN-сообщений на заданное время."""
        self.messages = []
        if can is None:
            logger.warning("python-can is not installed; CAN analyzer unavailable")
            return False

        try:
            self.bus = can.Bus(interface=self.interface, channel=self.channel, bitrate=self.bitrate)
        except Exception as exc:
            logger.error("Failed to initialize CAN bus: %s", exc)
            self.bus = None
            return False

        self.running = True
        started = time.time()
        timeout = max(1, int(duration))
        while self.running and (time.time() - started) < timeout:
            msg = self.bus.recv(timeout=0.1)
            if not msg:
                continue
            self.messages.append(
                {
                    "timestamp": getattr(msg, "timestamp", None),
                    "arbitration_id": getattr(msg, "arbitration_id", None),
                    "data": getattr(getattr(msg, "data", b""), "hex", lambda: "")(),
                    "dlc": getattr(msg, "dlc", None),
                    "is_extended_id": getattr(msg, "is_extended_id", None),
                }
            )

        if self.bus is not None:
            self.bus.shutdown()
        self.running = False
        return True

    def stop_monitoring(self) -> None:
        """Останавливает мониторинг."""
        self.running = False

    def analyze_uds(self) -> dict[str, Any]:
        """Базовая заглушка анализа UDS без активной передачи."""
        return {
            "uds_supported": False,
            "found_services": [],
            "note": "Пассивный режим: активные UDS-проверки в данной версии не выполняются.",
        }

    def get_statistics(self) -> dict[str, Any]:
        """Возвращает статистику собранных сообщений."""
        if not self.messages:
            return {"total_messages": 0, "unique_ids": 0, "bus_load_estimate": "unknown"}

        unique_ids = len({msg.get("arbitration_id") for msg in self.messages})
        total_messages = len(self.messages)

        if total_messages < 100:
            load = "low"
        elif total_messages < 1000:
            load = "medium"
        else:
            load = "high"

        return {
            "total_messages": total_messages,
            "unique_ids": unique_ids,
            "bus_load_estimate": load,
        }


# Backward-compatible alias for earlier scaffold imports.
CANAnalyzer = CANBusAnalyzer
