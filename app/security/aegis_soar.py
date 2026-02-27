import asyncio
import logging
import os

import httpx

logger = logging.getLogger(__name__)

CF_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")
CF_ZONE_ID = os.getenv("CLOUDFLARE_ZONE_ID")

_BLOCKED_ATTACKS = 0


def register_blocked_attack() -> None:
    global _BLOCKED_ATTACKS
    _BLOCKED_ATTACKS += 1


def get_blocked_attacks() -> int:
    """Return number of attacks blocked by SOAR runtime since process start."""
    return _BLOCKED_ATTACKS


async def block_ip_on_edge(ip_address: str, reason: str = "Aegis Autonomous Block"):
    """
    Отправляет команду в Cloudflare WAF на блокировку IP-адреса на уровне Edge.
    """
    if not ip_address:
        return False

    if not CF_API_TOKEN or not CF_ZONE_ID:
        logger.error("[AEGIS_SOAR] Токен Cloudflare не настроен. Симуляция блокировки.")
        logger.warning("[AEGIS_SOAR] [SIMULATION] IP %s заблокирован. Причина: %s", ip_address, reason)
        return False

    url = f"https://api.cloudflare.com/client/v4/zones/{CF_ZONE_ID}/firewall/access_rules/rules"
    headers = {
        "Authorization": f"Bearer {CF_API_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "mode": "block",
        "configuration": {"target": "ip", "value": ip_address},
        "notes": f"PLAYE_V4_AEGIS: {reason}",
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload, timeout=5.0)
            if response.status_code == 200:
                logger.critical("[AEGIS_SOAR] ВНИМАНИЕ! IP %s успешно заблокирован на уровне WAF!", ip_address)
                register_blocked_attack()
                return True

            logger.error("[AEGIS_SOAR] Ошибка WAF API: %s", response.text)
            return False
    except Exception as exc:
        logger.error("[AEGIS_SOAR] Ошибка соединения с WAF: %s", exc)
        return False


def block_ip_sync(ip_address: str, reason: str = "Aegis Autonomous Block") -> bool:
    """Синхронная обертка для интеграции в sync-контексты."""
    try:
        return asyncio.run(block_ip_on_edge(ip_address, reason))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(block_ip_on_edge(ip_address, reason))
        finally:
            loop.close()
            asyncio.set_event_loop(None)
