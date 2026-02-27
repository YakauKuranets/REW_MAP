# -*- coding: utf-8 -*-
"""Advanced OSINT scanner with Shodan and Censys support (defensive inventory)."""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

import requests
from compat_flask import current_app

logger = logging.getLogger(__name__)


class AdvancedOSINTScanner:
    """Combine Shodan/Censys APIs for vulnerability and history enrichment."""

    def __init__(self) -> None:
        cfg = current_app.config if current_app else {}
        self.shodan_api_key = (cfg.get("SHODAN_API_KEY") or "").strip()
        self.censys_api_id = (cfg.get("CENSYS_API_ID") or "").strip()
        self.censys_secret = (cfg.get("CENSYS_SECRET") or "").strip()
        self.shodan_base = "https://api.shodan.io"
        self.censys_base = "https://search.censys.io/api/v2"
        self.session = requests.Session()

    def search_by_cve(self, cve_id: str, country: Optional[str] = None) -> List[Dict]:
        results: list[dict] = []
        if not self.shodan_api_key:
            return results

        query = f"vuln:{(cve_id or '').strip()}"
        if country:
            query += f" country:{country.strip()}"

        try:
            resp = self.session.get(
                f"{self.shodan_base}/shodan/host/search",
                params={"key": self.shodan_api_key, "query": query},
                timeout=20,
            )
            if resp.status_code != 200:
                return results
            data = resp.json() or {}
            for match in data.get("matches", []) or []:
                results.append(
                    {
                        "source": "shodan",
                        "ip": match.get("ip_str"),
                        "port": match.get("port"),
                        "country": (match.get("location") or {}).get("country_name"),
                        "city": (match.get("location") or {}).get("city"),
                        "org": match.get("org"),
                        "cve": cve_id,
                    }
                )
        except Exception:
            logger.exception("Shodan search failed")

        return results

    def get_device_history(self, ip: str) -> Dict:
        if not (self.censys_api_id and self.censys_secret and ip):
            return {}

        try:
            resp = self.session.get(
                f"{self.censys_base}/hosts/{ip}",
                auth=(self.censys_api_id, self.censys_secret),
                timeout=20,
            )
            if resp.status_code != 200:
                return {}
            payload = resp.json() or {}
            data = payload.get("result") if isinstance(payload.get("result"), dict) else payload
            return {
                "ip": ip,
                "first_seen": data.get("first_seen"),
                "last_seen": data.get("last_seen"),
                "services": data.get("services", []),
                "tls_configs": self._extract_tls_history(data),
            }
        except Exception:
            logger.exception("Censys history failed")
            return {}

    def _extract_tls_history(self, data: Dict) -> List[Dict]:
        out: list[dict] = []
        for service in (data.get("services") or []):
            tls = service.get("tls") if isinstance(service, dict) else None
            if not isinstance(tls, dict):
                continue
            out.append(
                {
                    "port": service.get("port"),
                    "version": tls.get("version"),
                    "cipher_suites": tls.get("cipher_suites", []),
                }
            )
        return out
