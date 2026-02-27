# -*- coding: utf-8 -*-
"""
Сканер устройств Modbus/TCP для оценки доступности и базовой диагностики.
Используется для аудита промышленных сетей в авторизованном контуре.
"""

from __future__ import annotations

import logging
import socket
from typing import Any

logger = logging.getLogger(__name__)

try:
    from pymodbus.client import ModbusTcpClient
    from pymodbus.exceptions import ModbusException
except Exception:  # pragma: no cover - optional dependency
    ModbusTcpClient = None  # type: ignore[assignment]
    ModbusException = Exception  # type: ignore[assignment]


class ModbusDeviceScanner:
    """
    Сканирует IP-адреса на наличие Modbus/TCP и собирает базовую телеметрию
    (доступность порта, идентификатор/регистры при доступности клиента).
    """

    def __init__(self, timeout: float = 2.0):
        self.timeout = timeout

    def scan_ip(self, ip: str) -> dict[str, Any]:
        """Проверяет один IP-адрес на доступность Modbus сервера."""
        result: dict[str, Any] = {
            "ip": ip,
            "port_open": False,
            "device_id": None,
            "registers": {},
            "modbus_client_available": ModbusTcpClient is not None,
        }

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        try:
            sock.connect((ip, 502))
            result["port_open"] = True
        except OSError:
            return result
        finally:
            sock.close()

        if ModbusTcpClient is None:
            return result

        client = ModbusTcpClient(ip, port=502, timeout=self.timeout)
        if not client.connect():
            return result

        try:
            response_id = client.read_holding_registers(address=0, count=1, slave=1)
            if response_id is not None and not response_id.isError() and getattr(response_id, "registers", None):
                result["device_id"] = response_id.registers[0]

            response_regs = client.read_holding_registers(address=0, count=10, slave=1)
            if response_regs is not None and not response_regs.isError() and getattr(response_regs, "registers", None):
                for i, val in enumerate(response_regs.registers):
                    result["registers"][f"reg_{i}"] = val
        except ModbusException as exc:
            logger.debug("Modbus error for %s: %s", ip, exc)
        except Exception:
            logger.exception("Unexpected Modbus scan failure for %s", ip)
        finally:
            client.close()

        return result

    def scan_network(self, base_ip: str, first: int = 1, last: int = 254) -> list[dict[str, Any]]:
        """
        Сканирует диапазон IP-адресов в подсети.
        base_ip: первые три октета, например "192.168.1.".
        """
        found: list[dict[str, Any]] = []
        for host in range(max(first, 0), min(last, 254) + 1):
            ip = f"{base_ip}{host}"
            scan = self.scan_ip(ip)
            if scan["port_open"]:
                found.append(scan)
        return found


# Backward-compatible alias for earlier code.
ModbusScanner = ModbusDeviceScanner
