# -*- coding: utf-8 -*-
"""
Модуль сбора открытых данных об owned-активах компании (доменах, IP-диапазонах).
Использует публичные источники: crt.sh, Shodan, Censys.
Все данные обезличены и относятся только к инфраструктуре, которую мы обслуживаем.
"""

import asyncio
import logging
from typing import Dict, List

import requests

logger = logging.getLogger(__name__)


class PublicAssetDataCollector:
    """
    Собирает публичные данные об owned-активах из открытых источников.
    """

    def __init__(self, shodan_api_key: str = None, censys_api_id: str = None, censys_secret: str = None):
        self.shodan_api_key = shodan_api_key
        self.censys_api_id = censys_api_id
        self.censys_secret = censys_secret

    async def fetch_certificate_subdomains(self, domain: str) -> List[str]:
        """
        Получает поддомены для собственного домена из сертификатов crt.sh.
        """
        logger.info("[PUBLIC_DATA] Запрос поддоменов для %s из crt.sh", domain)
        try:
            url = f"https://crt.sh/?q=%25.{domain}&output=json"
            response = await asyncio.to_thread(requests.get, url, timeout=20)
            if response.status_code == 200:
                data = response.json()
                subdomains = set()
                for entry in data:
                    name = entry.get("name_value", "").lower()
                    if name and "*" not in name:
                        for sub in name.split("\n"):
                            sub = sub.strip()
                            if sub.endswith(f".{domain}"):
                                subdomains.add(sub)
                logger.info("[PUBLIC_DATA] Найдено %s поддоменов", len(subdomains))
                return sorted(subdomains)
        except Exception as exc:
            logger.error("[PUBLIC_DATA] Ошибка crt.sh: %s", exc)
        return []

    async def fetch_shodan_info(self, ip: str) -> Dict:
        """
        Получает информацию об IP (открытые порты, сервисы) из Shodan.
        """
        if not self.shodan_api_key:
            return {}
        try:
            url = f"https://api.shodan.io/shodan/host/{ip}?key={self.shodan_api_key}"
            response = await asyncio.to_thread(requests.get, url, timeout=20)
            if response.status_code == 200:
                return response.json()
        except Exception as exc:
            logger.error("[PUBLIC_DATA] Ошибка Shodan: %s", exc)
        return {}

    async def collect_asset_indicators(self, owned_domains: List[str]) -> List[Dict]:
        """
        Собирает все открытые данные по owned-доменам.
        Возвращает список записей с обезличенными индикаторами.
        """
        all_indicators: List[Dict] = []
        for domain in owned_domains:
            subs = await self.fetch_certificate_subdomains(domain)
            for sub in subs:
                indicator = {
                    "domain": sub,
                    "source": "crt.sh",
                    "timestamp": None,
                    "risk_flags": [],
                }
                all_indicators.append(indicator)
        return all_indicators
