# -*- coding: utf-8 -*-
"""Мониторинг постов darknet-форумов, SIEM и атрибуция угроз."""

from __future__ import annotations

import asyncio
import logging

from app.siem.exporter import SIEMExporter
from app.siem.models import EventSeverity
from app.threat_intel.attribution_engine import process_new_intel

logger = logging.getLogger(__name__)


def _enrich_attribution_graph(post: dict) -> None:
    """Обогащает граф атрибуции новой находкой из форума."""
    raw_intel = {
        "author": post.get("actor") or post.get("author") or "unknown_actor",
        "btc_wallet": post.get("btc_wallet"),
        "message_text": post.get("body") or post.get("content") or post.get("text"),
        "ip": post.get("ip"),
        "pgp_key": post.get("pgp_key"),
    }

    try:
        profile = asyncio.run(process_new_intel(raw_intel))
        logger.debug("[KRAKEN_GRAPH] Профиль актера обновлен: %s", profile)
    except RuntimeError:
        logger.debug("[KRAKEN_GRAPH] Active event loop detected, scheduling enrichment task")
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(process_new_intel(raw_intel))
        except RuntimeError:
            logger.exception("[KRAKEN_GRAPH] Failed to acquire running loop for enrichment")


def emit_new_post_event(post: dict) -> None:
    """Создаёт SIEM-событие при обнаружении нового поста с индикаторами."""
    if post.get("indicators"):
        exporter = SIEMExporter()
        exporter.create_event(
            source="darknet_monitor",
            category="threat_intel",
            title=f"New darknet post: {post.get('title', 'Unknown')}",
            description=f"Post from {post.get('actor', 'unknown')} on darknet forum",
            severity=EventSeverity.INFO.value,
            indicators=post.get("indicators"),
        )

    _enrich_attribution_graph(post)
