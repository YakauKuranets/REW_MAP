"""Telegram admin notifications helper."""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)


async def send_to_admin(text: str) -> bool:
    """Send notification to configured Telegram admin chat via Bot API."""
    bot_token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    admin_chat_id = (os.getenv("TELEGRAM_ALERT_CHAT_ID") or "").strip()

    if not bot_token or not admin_chat_id:
        logger.warning("Telegram notifications are not configured; skipping alert")
        return False

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": admin_chat_id, "text": text}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            return resp.status_code == 200
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to send Telegram alert: %s", exc)
        return False
