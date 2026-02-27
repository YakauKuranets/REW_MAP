# -*- coding: utf-8 -*-
"""
Модуль анализа Z-Wave сетей. Используется для инвентаризации устройств и проверки
корректности их работы в рамках авторизованной диагностики.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

try:
    from openzwave.network import ZWaveNetwork
    from openzwave.option import ZWaveOption
except Exception:  # pragma: no cover - optional dependency in many envs
    ZWaveNetwork = None  # type: ignore[assignment]
    ZWaveOption = None  # type: ignore[assignment]


class ZWaveNetworkAnalyzer:
    """Анализатор Z-Wave сети: inventory и базовая оценка статуса узлов."""

    def __init__(self, device_path: str = "/dev/ttyACM0"):
        self.device_path = device_path
        self.network: Optional[Any] = None

    def start(self) -> bool:
        """Запуск контроллера Z-Wave."""
        if ZWaveOption is None or ZWaveNetwork is None:
            logger.warning("openzwave is not installed; Z-Wave analyzer unavailable")
            return False

        options = ZWaveOption(self.device_path)
        options.lock()
        self.network = ZWaveNetwork(options, autostart=True)
        self.network.start()
        logger.info("Z-Wave analyzer started on %s", self.device_path)
        return True

    def scan_network(self, timeout: int = 30) -> list[dict[str, Any]]:
        """Сбор информации об узлах сети."""
        if self.network is None and not self.start():
            return []

        started = time.time()
        nodes: list[dict[str, Any]] = []

        state_ready = getattr(self.network, "STATE_READY", None)
        if state_ready is not None:
            while time.time() - started < max(timeout, 1):
                if getattr(self.network, "state", None) is not None and self.network.state >= state_ready:
                    break
                time.sleep(1)

        network_nodes = getattr(self.network, "nodes", {}) or {}
        iterable = network_nodes.values() if isinstance(network_nodes, dict) else network_nodes
        for node in iterable:
            nodes.append(
                {
                    "node_id": getattr(node, "node_id", None),
                    "manufacturer": getattr(node, "manufacturer_name", None),
                    "product": getattr(node, "product_name", None),
                    "type": getattr(node, "node_type", None),
                    "is_secure": getattr(node, "is_secure", None),
                    "capabilities": list(getattr(node, "capabilities", []) or []),
                    "battery_level": getattr(node, "battery_level", None),
                    "listening": getattr(node, "is_listening", None),
                    "frequent_listening": getattr(node, "is_frequent_listening", None),
                    "routing": getattr(node, "is_routing", None),
                    "beaming": getattr(node, "is_beaming", None),
                }
            )

        return nodes

    def stop(self) -> None:
        """Остановка контроллера."""
        if self.network:
            self.network.stop()
            self.network = None


# Backward-compatible alias used by earlier scaffold imports.
ZWaveAnalyzer = ZWaveNetworkAnalyzer
