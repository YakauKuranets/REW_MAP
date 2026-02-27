from __future__ import annotations

from celery import shared_task
from sqlalchemy import or_

from app.alerting.models import AlertHistory, AlertRule
from app.diagnostics.models import DiagnosticTarget
from app.extensions import db
from app.integrations.telegram_sender import send_telegram_message
from app.realtime import send_alert_to_dashboard
from app.vulnerabilities.models import CVE


@shared_task(name="app.alerting.checker.check_alerts")
def check_alerts() -> dict:
    """Проверка активных правил и отправка оповещений."""
    rules = AlertRule.query.filter_by(enabled=True).all()
    sent = 0

    for rule in rules:
        if rule.condition == "cvss_gt":
            sent += _process_cvss_rule(rule)
        elif rule.condition == "password_found":
            sent += _process_password_rule(rule)
        elif rule.condition == "device_compromised":
            sent += _process_compromised_rule(rule)

    db.session.commit()
    return {"rules": len(rules), "sent": sent}


def _process_cvss_rule(rule: AlertRule) -> int:
    threshold = float(rule.threshold or 7.0)
    cves = CVE.query.filter(CVE.cvss_score.isnot(None), CVE.cvss_score > threshold).all()
    sent = 0

    for cve in cves:
        fingerprint = f"CVE:{cve.id}"
        exists = AlertHistory.query.filter_by(rule_id=rule.id, message=fingerprint).first()
        if exists:
            continue

        text = (
            f"Критическая уязвимость обнаружена: {cve.id} (CVSS {cve.cvss_score})\n"
            f"{(cve.description or '')[:200]}"
        )
        _dispatch_alert(rule, text, severity="high")
        db.session.add(AlertHistory(rule_id=rule.id, message=fingerprint, severity="high"))
        sent += 1

    return sent


def _process_password_rule(rule: AlertRule) -> int:
    targets = DiagnosticTarget.query.filter(
        or_(
            DiagnosticTarget.risk_summary.ilike("%password%"),
            DiagnosticTarget.risk_summary.ilike("%парол%"),
        )
    ).all()
    sent = 0

    for target in targets:
        fingerprint = f"PASSWORD:{target.id}"
        exists = AlertHistory.query.filter_by(rule_id=rule.id, message=fingerprint).first()
        if exists:
            continue

        text = f"Найден риск раскрытия пароля на цели {target.identifier} (id={target.id})"
        _dispatch_alert(rule, text, severity="critical")
        db.session.add(AlertHistory(rule_id=rule.id, message=fingerprint, severity="critical"))
        sent += 1

    return sent


def _process_compromised_rule(rule: AlertRule) -> int:
    targets = DiagnosticTarget.query.filter(
        DiagnosticTarget.status.in_(["compromised", "critical"])
    ).all()
    sent = 0

    for target in targets:
        fingerprint = f"COMPROMISED:{target.id}"
        exists = AlertHistory.query.filter_by(rule_id=rule.id, message=fingerprint).first()
        if exists:
            continue

        text = f"Возможная компрометация устройства {target.identifier} (status={target.status})"
        _dispatch_alert(rule, text, severity="critical")
        db.session.add(AlertHistory(rule_id=rule.id, message=fingerprint, severity="critical"))
        sent += 1

    return sent


def _dispatch_alert(rule: AlertRule, text: str, *, severity: str) -> None:
    payload = {
        "rule_id": rule.id,
        "rule_name": rule.name,
        "condition": rule.condition,
        "severity": severity,
        "message": text,
    }

    if rule.channel == "telegram":
        from compat_flask import current_app

        token = current_app.config.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = current_app.config.get("TELEGRAM_ALERT_CHAT_ID", "")
        if token and chat_id:
            try:
                send_telegram_message(token, str(chat_id), text)
            except Exception:
                pass

    send_alert_to_dashboard(payload)
