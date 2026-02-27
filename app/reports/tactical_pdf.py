"""Generate tactical PDF briefing and notify command channel."""

from __future__ import annotations

import logging
from datetime import date, datetime
from pathlib import Path

from jinja2 import Template
from weasyprint import HTML

from app.bot.notifications import send_to_admin
from app.threat_intel.disinformation import poison_engine

logger = logging.getLogger(__name__)


def generate_morning_briefing(intercepted_nodes: int, blocked_attacks: int) -> str:
    today = date.today().isoformat()
    now = datetime.now().strftime("%H:%M:%S")
    logger.info("[ГЕНШТАБ] Компиляция тактической сводки за %s", today)

    template_str = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body { background-color: #0a0a0a; color: #00ffcc; font-family: 'Courier New', monospace; padding: 20px; }
            h1 { color: #ffaa00; text-transform: uppercase; border-bottom: 1px solid #00ffcc; }
            h2 { color: #00ffaa; }
            hr { border: 1px solid #336699; }
            .data { font-size: 1.2em; margin: 10px 0; }
            .footer { margin-top: 30px; font-size: 0.8em; color: #6699cc; }
        </style>
    </head>
    <body>
        <h1>PLAYE STUDIO PRO v6.0 — TACTICAL BRIEFING</h1>
        <h2>CLASSIFIED // EYES ONLY // QUANTUM-RESISTANT</h2>
        <hr>
        <p class="data"><strong>Дата:</strong> {{ date }}</p>
        <p class="data"><strong>Атак отражено (SOAR/eBPF):</strong> {{ blocked_attacks }}</p>
        <p class="data"><strong>Узлов аномалий (Neo4j):</strong> {{ intercepted_nodes }}</p>
        <p class="data"><strong>Статус defensive decoy simulation:</strong> АКТИВЕН</p>
        <p class="data"><strong>Синтетических агентов:</strong> {{ ghost_count }}</p>
        <hr>
        <p class="footer">END OF REPORT • {{ date }} {{ time }}</p>
    </body>
    </html>
    """

    html_content = Template(template_str).render(
        date=today,
        time=now,
        blocked_attacks=blocked_attacks,
        intercepted_nodes=intercepted_nodes,
        ghost_count=len(poison_engine.active_ghosts),
    )

    out = Path(f"/tmp/briefing_{today}.pdf")
    HTML(string=html_content).write_pdf(str(out))
    logger.warning("[ГЕНШТАБ] Отчёт скомпилирован: %s", out)
    return str(out)


async def send_briefing_to_command(intercepted_nodes: int, blocked_attacks: int) -> str:
    pdf_path = generate_morning_briefing(intercepted_nodes, blocked_attacks)
    await send_to_admin(
        f"[TACTICAL_BRIEFING] Новый PDF отчёт: {pdf_path} | nodes={intercepted_nodes} attacks={blocked_attacks}"
    )
    logger.info("[ГЕНШТАБ] Уведомление о сводке отправлено администратору")
    return pdf_path
