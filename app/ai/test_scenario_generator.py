# -*- coding: utf-8 -*-
"""
Модуль генерации тестовых сценариев для верификации уязвимостей на основе CVE.
Использует публичные данные NVD и языковую модель для создания проверочного кода.
Предназначен для authorised тестирования безопасности.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

import requests

from app.ai.predictive_advisor import PredictiveAdvisor

logger = logging.getLogger(__name__)


class TestScenarioGenerator:
    """Генератор сценариев для проверки уязвимостей."""

    NVD_API_BASE = "https://services.nvd.nist.gov/rest/json/cves/2.0"

    def __init__(self, llm_endpoint: Optional[str] = None):
        self.llm = PredictiveAdvisor(endpoint=llm_endpoint) if llm_endpoint else PredictiveAdvisor()

    def fetch_cve_details(self, cve_id: str) -> Dict:
        """Получает информацию об уязвимости из базы NVD."""
        try:
            response = requests.get(self.NVD_API_BASE, params={"cveId": cve_id}, timeout=10)
            if response.status_code != 200:
                return {}
            data = response.json() or {}
            vulns = data.get("vulnerabilities", [])
            if not vulns:
                logger.warning("CVE %s not found in NVD", cve_id)
                return {}

            cve_item = vulns[0].get("cve", {})
            descriptions = cve_item.get("descriptions", [])
            description = next((d.get("value", "") for d in descriptions if d.get("lang") == "en"), "")
            metrics = cve_item.get("metrics", {})
            cvss_v3 = metrics.get("cvssMetricV31", [{}])[0].get("cvssData", {})
            configurations = cve_item.get("configurations", [])

            return {
                "cve_id": cve_id,
                "description": description,
                "cvss_score": cvss_v3.get("baseScore"),
                "attack_vector": cvss_v3.get("attackVector"),
                "configurations": configurations,
                "raw": cve_item,
            }
        except Exception as exc:
            logger.error("Ошибка при запросе к NVD: %s", exc)
            return {}

    def generate_test_script(self, cve_details: Dict) -> str:
        """Генерирует проверочный безопасный скрипт с использованием LLM."""
        prompt = f"""
Based on the following CVE details, create a safe proof-of-concept script in Python or Bash to verify the vulnerability.
The script should be educational, non-destructive, and include comments explaining each step.
Use only standard libraries where possible. Output only the code without markdown.

CVE ID: {cve_details.get('cve_id')}
Description: {cve_details.get('description')}
CVSS Score: {cve_details.get('cvss_score')}
Attack Vector: {cve_details.get('attack_vector')}
Affected configurations: {cve_details.get('configurations')}
""".strip()
        return self.llm._call_llm(prompt, max_tokens=700) or ""

    def generate(self, cve_id: str) -> Dict:
        """Полный цикл: получение деталей CVE и генерация скрипта."""
        details = self.fetch_cve_details(cve_id)
        if not details:
            return {"cve_id": cve_id, "error": "CVE not found or no details available", "script": None}

        script = self.generate_test_script(details)
        return {
            "cve_id": cve_id,
            "description": details.get("description"),
            "cvss": details.get("cvss_score"),
            "script": script,
            "status": "generated" if script else "failed",
        }
