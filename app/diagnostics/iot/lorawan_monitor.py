# -*- coding: utf-8 -*-
"""
Модуль пассивного мониторинга LoRaWAN трафика.
Позволяет собирать статистику использования частот и анализировать активность устройств
в рамках авторизованной диагностики.
"""

from __future__ import annotations

import logging
import os
import subprocess
from typing import Any

logger = logging.getLogger(__name__)


class LoRaWANMonitor:
    """Мониторинг LoRaWAN трафика через внешний sniffer-инструмент."""

    def __init__(self, freq: float = 868.1e6, gain: int = 40, output_file: str = "/tmp/lorawan_dump.txt"):
        self.freq = freq
        self.gain = gain
        self.output_file = output_file
        self.process: subprocess.Popen[str] | None = None

    def start_monitor(self, duration: int = 60) -> bool:
        """Запускает sniffer на указанное время и пишет данные в output-файл."""
        cmd = [
            "gr-lora_sdr",
            "-f",
            str(self.freq),
            "-g",
            str(self.gain),
            "-o",
            self.output_file,
            "-t",
            str(max(1, duration)),
        ]
        try:
            self.process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            logger.info("LoRaWAN monitor started (freq=%s, gain=%s)", self.freq, self.gain)
            return True
        except FileNotFoundError:
            logger.warning("gr-lora_sdr is not installed; LoRaWAN monitor unavailable")
        except Exception:
            logger.exception("Failed to start LoRaWAN monitor")
        self.process = None
        return False

    def stop_monitor(self) -> None:
        """Остановка sniffer-процесса."""
        if self.process:
            self.process.terminate()
            self.process.wait(timeout=10)
            self.process = None
            logger.info("LoRaWAN monitor stopped")

    def parse_results(self) -> list[dict[str, Any]]:
        """Парсит output-файл и возвращает список обнаруженных пакетов."""
        packets: list[dict[str, Any]] = []
        if not os.path.exists(self.output_file):
            return packets

        with open(self.output_file, "r", encoding="utf-8", errors="ignore") as stream:
            for line in stream:
                parts = [p.strip() for p in line.strip().split(",")]
                if len(parts) < 5:
                    continue
                try:
                    packets.append(
                        {
                            "timestamp": parts[0],
                            "frequency": float(parts[1]),
                            "spreading_factor": int(parts[2]),
                            "crc_valid": parts[3] == "1",
                            "payload": parts[4],
                        }
                    )
                except (ValueError, TypeError):
                    logger.debug("Skipping malformed LoRaWAN line: %s", line.strip())
        return packets
