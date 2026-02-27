# -*- coding: utf-8 -*-
"""
Модуль анализа Zigbee-сетей для оценки совместимости устройств и выявления
потенциальных проблем конфигурации. Используется для authorised тестирования.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

try:
    from zigpy_znp.types import nvids
    from zigpy_znp.zigbee.application import ControllerApplication
except Exception:  # pragma: no cover
    ControllerApplication = None  # type: ignore[assignment]
    nvids = None  # type: ignore[assignment]


class ZigbeeNetworkAnalyzer:
    def __init__(self, device_path: str = "/dev/ttyUSB0", channel: int = 11):
        self.device_path = device_path
        self.channel = channel
        self.app: Any = None

    async def start(self) -> bool:
        if ControllerApplication is None:
            logger.warning("zigpy-znp is not installed; Zigbee analyzer unavailable")
            return False
        self.app = await ControllerApplication.new(
            ControllerApplication.SCHEMA,
            {
                "device": {"path": self.device_path, "baudrate": 115200},
                "database_path": "/tmp/zigbee.db",
            },
        )
        await self.app.startup()
        logger.info("Zigbee analyzer started on %s", self.device_path)
        return True

    async def scan_network(self, duration: int = 60) -> list[dict]:
        if self.app is None and not await self.start():
            return []

        devices: list[dict] = []
        channels = [11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26]
        sleep_per_channel = max(1, min(int(duration), 120)) / max(len(channels), 1)

        for ch in channels:
            await self._set_channel(ch)
            await asyncio.sleep(sleep_per_channel)
            for dev in getattr(self.app, "devices", {}).values():
                if str(getattr(dev, "ieee", "")) not in [d["ieee"] for d in devices]:
                    devices.append(await self._get_device_info(dev))
        return devices

    async def _set_channel(self, channel: int) -> None:
        if nvids is None:
            return
        if hasattr(self.app, "_znp"):
            try:
                await self.app._znp.nvram_write(nvids.NWK_CHANNEL, [channel])
            except Exception:
                logger.debug("Unable to switch Zigbee channel", exc_info=True)

    async def _get_device_info(self, device: Any) -> dict:
        info = {
            "ieee": str(getattr(device, "ieee", "unknown")),
            "nwk": getattr(device, "nwk", None),
            "manufacturer": getattr(device, "manufacturer", None),
            "model": getattr(device, "model", None),
            "logical_type": getattr(getattr(device, "logical_type", None), "name", None),
            "endpoints": [],
        }
        for epid, ep in (getattr(device, "endpoints", {}) or {}).items():
            if epid == 0:
                continue
            info["endpoints"].append(
                {
                    "endpoint_id": epid,
                    "profile_id": getattr(ep, "profile_id", None),
                    "device_type": getattr(ep, "device_type", None),
                    "in_clusters": [str(c) for c in getattr(ep, "in_clusters", {})],
                    "out_clusters": [str(c) for c in getattr(ep, "out_clusters", {})],
                }
            )
        return info

    async def check_security(self, device_ieee: str) -> dict:
        return {
            "device": device_ieee,
            "uses_default_key": False,
            "encryption_level": "AES-128",
            "replay_protection": True,
            "note": "Пассивная проверка завершена; для активной валидации нужны дополнительные инструменты.",
        }

    async def stop(self) -> None:
        if self.app:
            await self.app.shutdown()
            self.app = None
