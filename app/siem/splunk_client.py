# -*- coding: utf-8 -*-
"""
Клиент для отправки событий в Splunk через HTTP Event Collector (HEC) и REST API.
Следует официальной документации Splunk по приёму данных.
"""

import logging
from typing import Any

import requests

from app.siem.models import SIEMEvent, SIEMExportConfig

logger = logging.getLogger(__name__)


class SplunkClient:
    """Клиент для взаимодействия с Splunk."""

    def __init__(self, config: SIEMExportConfig):
        self.config = config
        self.session = requests.Session()
        self.session.verify = config.ssl_verify

        if config.hec_token:
            self.session.headers.update(
                {
                    "Authorization": f"Splunk {config.hec_token}",
                    "Content-Type": "application/json",
                }
            )

    def send_event_hec(self, event: SIEMEvent) -> bool:
        """Отправляет одно событие через HTTP Event Collector."""
        hec_url = f"{self.config.endpoint}/services/collector/event"
        hec_event = self._to_hec(event)

        try:
            response = self.session.post(hec_url, json=hec_event, timeout=10)
            if response.status_code == 200:
                logger.info("Event %s sent to Splunk HEC", event.event_id)
                return True
            logger.error("Splunk HEC error: %s - %s", response.status_code, response.text)
            return False
        except requests.exceptions.RequestException as exc:
            logger.error("Splunk connection error: %s", exc)
            return False

    def send_batch_hec(self, events: list[SIEMEvent]) -> dict[str, Any]:
        """Отправляет пакет событий через HEC."""
        hec_url = f"{self.config.endpoint}/services/collector/event"
        batch = [self._to_hec(event) for event in events]

        try:
            response = self.session.post(hec_url, json=batch, timeout=30)
            if response.status_code == 200:
                logger.info("Batch of %s events sent to Splunk HEC", len(events))
                return {"success": True, "count": len(events)}
            logger.error("Splunk batch error: %s - %s", response.status_code, response.text)
            return {"success": False, "error": response.text}
        except requests.exceptions.RequestException as exc:
            logger.error("Splunk connection error: %s", exc)
            return {"success": False, "error": str(exc)}

    def send_metric(self, metric_name: str, value: float, dimensions: dict | None = None) -> bool:
        """Отправляет метрику через REST API."""
        api_url = f"{self.config.endpoint}/v2/datapoint"

        payload = {"gauge": [{"metric": metric_name, "value": value, "dimensions": dimensions or {}}]}
        headers = {"Content-Type": "application/json", "X-SF-TOKEN": self.config.auth_token}

        try:
            response = self.session.post(api_url, json=payload, headers=headers, timeout=10)
            return response.status_code == 200
        except requests.exceptions.RequestException as exc:
            logger.error("Failed to send metric: %s", exc)
            return False

    @staticmethod
    def _to_hec(event: SIEMEvent) -> dict[str, Any]:
        return {
            "time": event.created_at.timestamp(),
            "host": "xgen-platform",
            "source": event.source,
            "sourcetype": "_json",
            "event": {
                "event_id": event.event_id,
                "category": event.category,
                "severity": event.severity,
                "title": event.title,
                "description": event.description,
                "indicators": event.indicators,
                "targets": event.targets,
                "data": event.event_data,
            },
        }
