from __future__ import annotations

import os
import tempfile

from celery import shared_task

from app.diagnostics.models import AlertSubscription
from app.reports.email_sender import ReportMailer
from app.reports.generator import generate_report


@shared_task(name="app.tasks.reports_delivery.send_task_report_email")
def send_task_report_email(task_id: int, to_emails: list[str], subject: str | None = None, body: str | None = None):
    """Generate a diagnostic PDF and deliver it to recipients via email."""
    output = f"{tempfile.gettempdir()}/diagnostic_report_{int(task_id)}.pdf"
    report_path = generate_report(task_id, output)

    mailer = ReportMailer()
    ok = mailer.send_report(
        to_emails=to_emails,
        subject=subject or f"Diagnostic report #{task_id}",
        body=body or "Во вложении автоматический диагностический отчёт.",
        pdf_path=report_path,
    )
    return {"ok": bool(ok), "task_id": int(task_id), "report": report_path}


@shared_task(name="app.tasks.reports_delivery.generate_and_email_report")
def generate_and_email_report(task_id: int, recipient_emails: list[str]):
    """Generate report, email it, then remove temporary PDF."""
    output = f"{tempfile.gettempdir()}/report_{int(task_id)}.pdf"
    report_path = generate_report(task_id, output)
    mailer = ReportMailer()
    ok = mailer.send_report(
        to_emails=recipient_emails,
        subject=f"Диагностический отчёт по задаче {task_id}",
        body=f"Отчёт по диагностике цели {task_id} во вложении.",
        pdf_path=report_path,
    )

    try:
        if report_path and os.path.exists(report_path):
            os.remove(report_path)
    except Exception:
        pass

    return {"ok": bool(ok), "task_id": int(task_id)}


@shared_task(name="app.tasks.reports_delivery.send_vulnerability_alerts")
def send_vulnerability_alerts(cve_id: str, description: str, cvss_score: float, affected_devices: str):
    """Notify active subscribers about high-severity vulnerabilities."""
    score = float(cvss_score or 0)
    subs = AlertSubscription.query.filter(
        AlertSubscription.is_active.is_(True),
        AlertSubscription.min_severity <= score,
    ).all()
    if not subs:
        return {"ok": True, "sent": 0}

    mailer = ReportMailer()
    subject = f"⚠️ Критическая уязвимость: {cve_id}"
    body = (
        "Обнаружена критическая уязвимость:\n"
        f"ID: {cve_id}\n"
        f"CVSS: {score}\n"
        f"Описание: {description}\n"
        f"Затронутые устройства: {affected_devices}"
    )

    sent = 0
    for sub in subs:
        if mailer.send_report([sub.email], subject, body):
            sent += 1

    return {"ok": True, "sent": sent, "subscribers": len(subs)}
