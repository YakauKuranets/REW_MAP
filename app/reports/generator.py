from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

from app.diagnostics.models import DiagnosticTarget
from app.vulnerabilities.models import CVE


class ReportGenerationError(RuntimeError):
    pass


def _safe_value(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, (dict, list)):
        return str(value)
    return str(value)


def generate_report(task_id: int, output_path: str) -> str:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import Table, TableStyle
        from reportlab.pdfgen import canvas
    except Exception as exc:  # pragma: no cover
        raise ReportGenerationError("reportlab is not installed") from exc

    task = DiagnosticTarget.query.get(task_id)
    if not task:
        raise ReportGenerationError(f"task {task_id} not found")

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    c = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4

    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, height - 50, f"Диагностический отчёт: {task.identifier}")

    c.setFont("Helvetica", 10)
    c.drawString(50, height - 70, f"Дата: {dt.datetime.now().strftime('%Y-%m-%d %H:%M')}")
    c.drawString(50, height - 86, f"Тип объекта мониторинга: {task.target_type}")
    c.drawString(50, height - 102, f"Статус: {task.status}")

    y = height - 130
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "Обнаруженные несоответствия")
    y -= 18
    c.setFont("Helvetica", 10)
    nonconformities = task.nonconformities or []
    if not nonconformities:
        c.drawString(60, y, "Существенные несоответствия не выявлены.")
        y -= 16
    else:
        for item in nonconformities:
            c.drawString(60, y, f"• {_safe_value(item)[:120]}")
            y -= 14
            if y < 80:
                c.showPage()
                y = height - 50

    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "Риски")
    y -= 18
    c.setFont("Helvetica", 10)
    c.drawString(60, y, _safe_value(task.risk_summary)[:140])
    y -= 24

    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "Рекомендации по усилению")
    y -= 18
    c.setFont("Helvetica", 10)
    recommendations = task.recommendations or []
    if not recommendations:
        c.drawString(60, y, "Дополнительные рекомендации не сформированы.")
        y -= 16
    else:
        for rec in recommendations:
            c.drawString(60, y, f"• {_safe_value(rec)[:120]}")
            y -= 14
            if y < 80:
                c.showPage()
                y = height - 50

    context = task.context or {}
    model = context.get("model") if isinstance(context, dict) else None
    if model:
        cves = CVE.query.filter(CVE.affected_products.isnot(None)).all()
        matched = [cve for cve in cves if model.lower() in str(cve.affected_products).lower()]
        if matched:
            if y < 260:
                c.showPage()
                y = height - 50
            c.setFont("Helvetica-Bold", 12)
            c.drawString(50, y, "Связанные записи CVE")
            y -= 20
            data = [["CVE ID", "CVSS", "Описание"]]
            for cve in matched[:10]:
                data.append([cve.id, _safe_value(cve.cvss_score), (_safe_value(cve.description))[:80]])

            table = Table(data, colWidths=[90, 50, 360])
            table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, -1), 8),
                        ("GRID", (0, 0), (-1, -1), 1, colors.black),
                    ]
                )
            )
            table.wrapOn(c, width - 100, height)
            table.drawOn(c, 50, y - 180)

    c.save()
    return str(path)
