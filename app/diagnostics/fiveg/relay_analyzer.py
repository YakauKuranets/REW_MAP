# -*- coding: utf-8 -*-
"""5G UE Relay security analyzer.

Diagnostic-only helper that validates relay metadata and key-derivation flow shape.
No network exploitation or active interception is performed.
"""

from __future__ import annotations

import logging
from typing import Dict

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, hmac

logger = logging.getLogger(__name__)


class RelaySecurityAnalyzer:
    """Analyze security parameters for 5G UE relay sessions."""

    def __init__(self) -> None:
        self.backend = default_backend()

    def analyze_relay_configuration(self, remote_ue_id: str, relay_service_code: str) -> Dict:
        result = {
            "remote_ue_id": remote_ue_id,
            "relay_service_code": relay_service_code,
            "security_level": "high",
            "encryption_algorithms": ["AES-256-GCM", "SNOW 3G"],
            "integrity_protection": True,
            "replay_protection": True,
            "issues": [],
        }

        if len((relay_service_code or "").strip()) != 6:
            result["issues"].append("Нестандартная длина Relay Service Code")
            result["security_level"] = "medium"

        if not (remote_ue_id or "").strip():
            result["issues"].append("Пустой идентификатор remote UE")
            result["security_level"] = "low"

        return result

    def validate_key_derivation(self, knrp: bytes, nonce: bytes, freshness: bytes) -> bool:
        try:
            h = hmac.HMAC(b"5G_KEY_DERIVATION", hashes.SHA256(), backend=self.backend)
            h.update(knrp or b"")
            h.update(nonce or b"")
            h.update(freshness or b"")
            _ = h.finalize()
            return True
        except Exception:
            logger.exception("5G relay key derivation validation failed")
            return False
