# -*- coding: utf-8 -*-
"""Stealth SOCMINT scraper for profile discovery on public social pages."""

from __future__ import annotations

import logging
from typing import Any

from playwright_stealth import stealth_async

logger = logging.getLogger(__name__)


async def extract_social_profiles(alias: str, browser_context: Any) -> list[dict[str, Any]]:
    """Searches public profile URLs across platforms and returns lightweight hits."""
    normalized_alias = (alias or "").strip().lstrip("@")
    if not normalized_alias:
        return []

    platforms = [
        {"name": "INSTAGRAM", "url": f"https://www.instagram.com/{normalized_alias}/"},
        {"name": "FACEBOOK", "url": f"https://www.facebook.com/{normalized_alias}"},
        {"name": "LINKEDIN", "url": f"https://www.linkedin.com/in/{normalized_alias}"},
    ]

    findings: list[dict[str, Any]] = []
    page = await browser_context.new_page()
    await stealth_async(page)

    for platform in platforms:
        try:
            logger.info("[SOCMINT] Checking %s for alias %s", platform["name"], normalized_alias)
            response = await page.goto(platform["url"], timeout=15000, wait_until="domcontentloaded")
            status = response.status if response else None
            if status in {200, 301, 302}:
                title = await page.title()
                findings.append(
                    {
                        "platform": platform["name"],
                        "url": platform["url"],
                        "bio_snippet": title,
                        "confidence": 80,
                    }
                )
                logger.warning("[SOCMINT_HIT] Public profile candidate on %s: %s", platform["name"], platform["url"])
        except Exception as exc:
            logger.debug("[SOCMINT] %s unavailable or not found: %s", platform["name"], exc)

    await page.close()
    return findings
