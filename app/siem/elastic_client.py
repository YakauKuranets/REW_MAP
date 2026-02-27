# -*- coding: utf-8 -*-
"""
Клиент для отправки событий в Elasticsearch.
Использует официальный Python клиент Elasticsearch.
"""

import logging
from typing import Any

from app.siem.models import SIEMEvent, SIEMExportConfig

logger = logging.getLogger(__name__)


class ElasticClient:
    """Клиент для Elasticsearch/OpenSearch."""

    def __init__(self, config: SIEMExportConfig):
        self.config = config
        self.client = self._create_client()

    def _create_client(self):
        from elasticsearch import Elasticsearch

        if self.config.endpoint.startswith("http"):
            hosts: list[Any] = [self.config.endpoint]
        else:
            hosts = [{"host": self.config.endpoint, "port": 9200}]

        if self.config.auth_token and ":" in self.config.auth_token:
            username, password = self.config.auth_token.split(":", 1)
            return Elasticsearch(hosts, basic_auth=(username, password), verify_certs=self.config.ssl_verify)
        if self.config.auth_token:
            return Elasticsearch(hosts, api_key=self.config.auth_token, verify_certs=self.config.ssl_verify)
        return Elasticsearch(hosts, verify_certs=self.config.ssl_verify)

    def index_event(self, event: SIEMEvent) -> bool:
        """Индексирует одно событие в Elasticsearch."""
        doc = self._to_document(event)

        try:
            self.client.index(index=self.config.index_name, document=doc, id=event.event_id, refresh=False)
            logger.info("Event %s indexed to Elasticsearch", event.event_id)
            return True
        except Exception as exc:
            logger.error("Elasticsearch indexing error: %s", exc)
            return False

    def bulk_index(self, events: list[SIEMEvent]) -> dict[str, Any]:
        """Массовая индексация событий через Bulk API."""
        from elasticsearch import helpers

        actions = [
            {
                "_index": self.config.index_name,
                "_id": event.event_id,
                "_source": self._to_document(event),
            }
            for event in events
        ]

        try:
            success, errors = helpers.bulk(self.client, actions, stats_only=False, raise_on_error=False)
            logger.info("Bulk indexed %s events, %s failed", success, len(errors))
            return {"success": success, "failed": len(errors)}
        except Exception as exc:
            logger.error("Elasticsearch bulk error: %s", exc)
            return {"success": 0, "failed": len(events), "error": str(exc)}

    def _to_document(self, event: SIEMEvent) -> dict[str, Any]:
        return {
            "@timestamp": event.created_at.isoformat(),
            "event_id": event.event_id,
            "source": event.source,
            "category": event.category,
            "severity": event.severity,
            "severity_label": self._severity_to_label(event.severity),
            "title": event.title,
            "description": event.description,
            "indicators": event.indicators,
            "targets": event.targets,
            "data": event.event_data,
            "host": "xgen-platform",
        }

    @staticmethod
    def _severity_to_label(severity: int) -> str:
        mapping = {
            0: "EMERGENCY",
            1: "ALERT",
            2: "CRITICAL",
            3: "ERROR",
            4: "WARNING",
            5: "NOTICE",
            6: "INFO",
            7: "DEBUG",
        }
        return mapping.get(severity, "UNKNOWN")
