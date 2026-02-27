# -*- coding: utf-8 -*-
"""Profinet analyzer for industrial inventory and security assessment.

Performs basic DCP identify request/response capture on local segment.
"""

from __future__ import annotations

import logging
import struct
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class ProfinetAnalyzer:
    """Обнаружение и анализ устройств Profinet в локальной сети."""

    DCP_PORT = 34964
    ETHERTYPE_PN_DCP = 0x8892
    DCP_DST_MAC = "01:0e:cf:00:00:00"

    def __init__(self, interface: str = "eth0") -> None:
        self.interface = interface

    def discover_devices(self, timeout: int = 5) -> List[Dict[str, Any]]:
        """Send DCP Identify and parse best-effort responses."""
        try:
            from scapy.all import Ether, Raw, sendp, sniff
        except Exception:
            logger.warning("scapy is not installed; Profinet discovery unavailable")
            return []

        packet = Ether(dst=self.DCP_DST_MAC, type=self.ETHERTYPE_PN_DCP) / Raw(load=self._build_dcp_identify())

        try:
            responses = sniff(
                iface=self.interface,
                timeout=max(1, int(timeout)),
                started_callback=lambda: sendp(packet, iface=self.interface, verbose=False),
                store=True,
            )
        except Exception:
            logger.exception("Profinet sniff/send failed on iface=%s", self.interface)
            return []

        devices: list[dict[str, Any]] = []
        for pkt in responses:
            parsed = self._parse_dcp_response(pkt)
            if parsed:
                devices.append(parsed)
        return devices

    def _build_dcp_identify(self) -> bytes:
        """Build minimal DCP Identify request body."""
        return struct.pack("!BBHH", 0x05, 0x00, 0x0000, 0x0000)

    def _parse_dcp_response(self, packet: Any) -> Dict[str, Any]:
        """Parse packet into normalized device info."""
        try:
            mac = getattr(packet, "src", None)
            if not mac:
                return {}

            ip_value = None
            if packet.haslayer("IP"):
                ip_value = packet.getlayer("IP").src

            text_blob = bytes(packet).hex()[:256]
            return {
                "mac": mac,
                "ip": ip_value,
                "vendor": "Siemens" if "7369656d656e73" in text_blob else "Unknown",
                "name": "PN-Device",
            }
        except Exception:
            return {}
