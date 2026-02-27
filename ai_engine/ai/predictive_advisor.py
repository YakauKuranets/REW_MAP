# -*- coding: utf-8 -*-
"""
Интеллектуальный модуль предиктивного анализа (defensive-only).
---------------------------------------------------------------
Использует локальную языковую модель для генерации контекстно-зависимых
рекомендаций и сценариев диагностических проверок.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

import requests

try:
    from app.config import Config
except Exception:
    class Config:
        LLM_MODEL = "mistral"
        LLM_ENDPOINT = "http://localhost:11434/api/generate"

logger = logging.getLogger(__name__)


class PredictiveAdvisor:
    """LLM-советник для defensive рекомендаций и планирования проверок."""

    def __init__(self, model: str | None = None, endpoint: str | None = None):
        self.model = model or getattr(Config, "LLM_MODEL", "mistral")
        self.endpoint = endpoint or getattr(Config, "LLM_ENDPOINT", "") or "http://localhost:11434/api/generate"
        self._session = requests.Session()

    def _call_llm(self, prompt: str, max_tokens: int = 500) -> Optional[str]:
        try:
            response = self._session.post(
                self.endpoint,
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"num_predict": max_tokens},
                },
                timeout=30,
            )
            if response.status_code == 200:
                data = response.json() or {}
                return data.get("response")
            logger.error("LLM request failed with status %s", response.status_code)
        except Exception as exc:
            logger.exception("LLM call error: %s", exc)
        return None

    def suggest_test_scenarios(self, context: dict[str, Any], count: int = 8) -> list[str]:
        """Генерирует приоритизированные сценарии диагностических проверок."""
        prompt = (
            "You are an expert in defensive security diagnostics. "
            f"Given this context: {json.dumps(context, ensure_ascii=False)}. "
            f"Suggest up to {count} most useful SECURITY DIAGNOSTIC scenarios. "
            "Return only a JSON list of strings. Do not include offensive instructions."
        )
        answer = self._call_llm(prompt)
        return self._extract_json_string_list(answer)

    def analyze_previous_results(self, results: list[dict[str, Any]]) -> list[str]:
        """Анализирует прошлые результаты и предлагает улучшения defensive-процесса."""
        prompt = (
            "You help improve authorized security diagnostics. "
            f"Previous results: {json.dumps(results, ensure_ascii=False)}. "
            "Suggest up to 5 concrete improvements for risk reduction and coverage. "
            "Return only a JSON list of strings."
        )
        answer = self._call_llm(prompt)
        return self._extract_json_string_list(answer)

    def suggest_remediation_actions(self, findings: list[dict[str, Any]], count: int = 10) -> list[str]:
        """Формирует список remediation-шагов по найденным рискам."""
        prompt = (
            "You are a blue-team advisor. "
            f"Findings: {json.dumps(findings, ensure_ascii=False)}. "
            f"Provide up to {count} prioritized remediation actions. "
            "Return only a JSON list of strings."
        )
        answer = self._call_llm(prompt)
        return self._extract_json_string_list(answer)

    def adapt_model(self, successful_examples: list[dict[str, Any]]) -> None:
        """Заглушка адаптации: фиксируем few-shot примеры для последующего использования."""
        logger.info("Collected %s successful defensive examples for future prompt adaptation", len(successful_examples))

    @staticmethod
    def _extract_json_string_list(answer: str | None) -> list[str]:
        if not answer:
            return []
        match = re.search(r"\[.*\]", answer, re.DOTALL)
        if not match:
            return []
        try:
            payload = json.loads(match.group(0))
            if isinstance(payload, list):
                return [str(x).strip() for x in payload if str(x).strip()]
        except json.JSONDecodeError:
            logger.warning("Failed to parse LLM response as JSON list")
        return []


async def analyze_threat_context(raw_text: str, source: str) -> dict[str, Any]:
    """Async helper for ai_engine API: analyze threat context with LLM advisor."""
    advisor = PredictiveAdvisor()
    context = {"raw_text": raw_text, "source": source}
    scenarios = advisor.suggest_test_scenarios(context, count=5)
    improvements = advisor.analyze_previous_results([{"source": source, "text": raw_text[:500]}])
    return {"scenarios": scenarios, "improvements": improvements}
