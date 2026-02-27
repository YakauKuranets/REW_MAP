# -*- coding: utf-8 -*-
"""Фоновые задачи диагностики безопасности."""

import asyncio
import logging

import requests
from celery import shared_task

from app.ai.test_scenario_generator import TestScenarioGenerator
from app.diagnostics.models import DiagnosticTarget
from app.extensions import db
from app.network.proxy_client import get_proxy_session
from app.ai.red_swarm_coordinator import run_nightly_swarm

logger = logging.getLogger(__name__)


@shared_task
def run_security_scan(task_id: int | None, target: str, profile: str, use_proxy: bool = True, context: str | None = None):
    """Выполняет диагностическую задачу. Для AI_TEST_GEN генерирует сценарий по CVE."""
    logger.info("Запуск диагностики %s для %s (прокси=%s, context=%s)", profile, target, use_proxy, context)

    profile_aliases = {"WEB_DIR_ENUM": "WEB_DIR_SCAN", "OSINT_RECON": "OSINT_DEEP"}
    normalized_profile = profile_aliases.get(profile, profile)

    target_record = DiagnosticTarget.query.get(task_id) if task_id else None

    if normalized_profile == "AI_TEST_GEN":
        if not context:
            if target_record:
                target_record.status = "failed"
                target_record.result = {"error": "CVE context is required"}
                db.session.commit()
            return {"status": "failed", "error": "CVE context is required"}

        generator = TestScenarioGenerator()
        result = generator.generate(context)
        payload = {
            "script": result.get("script"),
            "cve": result.get("cve_id"),
            "description": result.get("description"),
            "cvss": result.get("cvss"),
        }
        if target_record:
            target_record.result = payload
            target_record.status = "completed" if result.get("script") else "failed"
            db.session.commit()
        return result

    session = get_proxy_session() if use_proxy else requests.Session()
    result = {
        "status": "completed",
        "target": target,
        "profile": normalized_profile,
        "use_proxy": use_proxy,
        "context": context,
        "details": {},
    }

    if normalized_profile == "PORT_SCAN":
        result["details"] = {"note": "PORT_SCAN queued (stub)."}
    elif normalized_profile == "WEB_DIR_SCAN":
        try:
            resp = session.get(f"https://{target}", timeout=8)
            result["details"] = {"http_status": resp.status_code}
        except Exception as exc:
            result["details"] = {"error": str(exc)}
    elif normalized_profile == "OSINT_DEEP":
        result["details"] = {"note": "OSINT_DEEP queued (stub)."}
    elif normalized_profile == "PHISHING_SIMULATION":
        result["details"] = {"note": f"Phishing simulation queued for {context or 'N/A'}"}

    if target_record:
        target_record.result = result
        target_record.status = "completed"
        db.session.commit()

    return result


@shared_task(name="app.tasks.diagnostics_tasks.trigger_red_swarm")
def trigger_red_swarm():
    """Celery task wrapper для ночного AI-аудита Red Swarm."""
    logger.warning("[RED_SWARM] Triggered from Celery Beat")
    try:
        report_path = asyncio.run(run_nightly_swarm())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            report_path = loop.run_until_complete(run_nightly_swarm())
        finally:
            loop.close()
            asyncio.set_event_loop(None)

    return {"status": "completed", "report_path": report_path}
