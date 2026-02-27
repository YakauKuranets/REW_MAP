"""Defensive synthetic-traffic generator for resilience testing.

This module generates *simulated* telemetry ghosts for internal QA/honeypot validation.
It does not broadcast to external channels directly.
"""

from __future__ import annotations

import asyncio
import logging
import random
from uuid import uuid4

logger = logging.getLogger(__name__)


class SyndromePoisoner:
    def __init__(self) -> None:
        self.active_ghosts: list[dict] = []
        self.base_lat = 55.7558
        self.base_lon = 37.6173

    async def generate_ghost_swarm(self, count: int = 5000) -> list[dict]:
        """Create synthetic decoy agents for defensive simulation."""
        logger.warning(
            "[DECOY_SIM] Генерация %s синтетических агентов для defensive-симуляции.",
            count,
        )

        swarm: list[dict] = []
        for _ in range(count):
            swarm.append(
                {
                    "id": str(uuid4()),
                    "lat": self.base_lat + random.uniform(-0.2, 0.2),
                    "lon": self.base_lon + random.uniform(-0.2, 0.2),
                    "fake_imsi": f"25099{random.randint(1000000000, 9999999999)}",
                    "simulated_device": random.choice(
                        [
                            "RISC-V Node",
                            "Android 13 SE",
                            "LoRa_Relay",
                            "MeshPoint v2",
                            "CryptoPhone",
                            "SatSleeve",
                        ]
                    ),
                    "signal_strength": random.randint(-90, -30),
                    "timestamp": asyncio.get_event_loop().time(),
                }
            )

        self.active_ghosts = swarm
        logger.info("[DECOY_SIM] Сгенерировано %s синтетических сигнатур.", len(self.active_ghosts))
        return self.active_ghosts

    async def broadcast_ghosts(self, interval: int = 10) -> None:
        """Emit local debug heartbeat for active synthetic signatures."""
        while True:
            if self.active_ghosts:
                ghost = random.choice(self.active_ghosts)
                logger.debug("[DECOY_SIM] heartbeat ghost=%s", ghost["id"])
            await asyncio.sleep(interval)


poison_engine = SyndromePoisoner()
