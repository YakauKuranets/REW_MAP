from __future__ import annotations

from typing import Any

from app.ai.predictive_advisor import PredictiveAdvisor


class TaskCoordinator:
    """Rule-based координатор с optional LLM-подсказками (defensive scope)."""

    def __init__(self, use_llm: bool = True):
        self.use_llm = use_llm
        self.advisor = PredictiveAdvisor() if use_llm else None

    def plan_tasks(self, target: Any) -> list[dict[str, Any]]:
        tasks: list[dict[str, Any]] = self._plan_rule_based(target)

        if self.use_llm and self.advisor:
            context = {
                "type": getattr(target, "type", ""),
                "identifier": getattr(target, "identifier", ""),
                **(getattr(target, "context", None) or {}),
            }
            scenarios = self.advisor.suggest_test_scenarios(context, count=5)
            for idx, scenario in enumerate(scenarios, start=1):
                tasks.append({
                    "type": "scenario_review",
                    "priority": 100 + idx,
                    "params": {"summary": scenario},
                })

        return sorted(tasks, key=lambda t: int(t.get("priority", 100)))

    @staticmethod
    def _plan_rule_based(target: Any) -> list[dict[str, Any]]:
        target_type = (getattr(target, "type", "") or "").lower()
        identifier = getattr(target, "identifier", None)
        if target_type == "wifi":
            return [
                {"type": "wifi_scan", "priority": 1, "params": {"bssid": identifier}},
                {"type": "pmkid_check", "priority": 2, "params": {"target_bssid": identifier}},
            ]
        if target_type == "ble":
            return [
                {"type": "ble_profile", "priority": 1, "params": {"address": identifier}},
                {"type": "ble_vuln_check", "priority": 2, "params": {"address": identifier}},
            ]
        if target_type == "ip":
            return [
                {"type": "port_scan", "priority": 1, "params": {"ip": identifier}},
                {"type": "web_audit", "priority": 2, "params": {"ip": identifier}},
            ]
        return []
