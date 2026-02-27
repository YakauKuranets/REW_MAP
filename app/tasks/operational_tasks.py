"""Operational daily briefing tasks."""

from __future__ import annotations

import asyncio

from celery import shared_task

from app.reports.tactical_pdf import send_briefing_to_command
from app.security.aegis_soar import get_blocked_attacks
from app.threat_intel.radio_hunter import hunter_engine


@shared_task(name="app.tasks.operational_tasks.daily_tactical_briefing")
def daily_tactical_briefing() -> str:
    suspects = hunter_engine.find_anomalous_towers()
    intercepted_nodes = len(suspects)
    blocked_attacks = get_blocked_attacks()

    asyncio.run(send_briefing_to_command(intercepted_nodes, blocked_attacks))
    return f"Briefing sent: {intercepted_nodes} nodes, {blocked_attacks} attacks."
