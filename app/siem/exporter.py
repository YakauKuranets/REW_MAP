# -*- coding: utf-8 -*-
"""
Модуль экспорта событий в SIEM системы.
Управляет очередью событий и отправкой в настроенные SIEM-инстансы.
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

from app.extensions import db
from app.siem.elastic_client import ElasticClient
from app.siem.models import EventSeverity, SIEMEvent, SIEMExportConfig
from app.siem.splunk_client import SplunkClient

logger = logging.getLogger(__name__)


class SIEMExporter:
    """Экспортёр событий в SIEM системы."""

    def __init__(self):
        self.clients: dict[int, Any] = {}
        self._load_clients()

    def _load_clients(self) -> None:
        configs = SIEMExportConfig.query.filter_by(is_active=True).all()
        for config in configs:
            if config.siem_type == "splunk":
                self.clients[config.id] = SplunkClient(config)
            elif config.siem_type in ["elastic", "opensearch"]:
                self.clients[config.id] = ElasticClient(config)

    def create_event(
        self,
        source: str,
        category: str,
        title: str,
        description: str,
        severity: int = EventSeverity.INFO.value,
        event_data: dict | None = None,
        indicators: dict | None = None,
        targets: dict | None = None,
    ) -> SIEMEvent:
        """Создаёт событие для отправки в SIEM."""
        event = SIEMEvent(
            event_id=str(uuid.uuid4()),
            source=source,
            category=category,
            severity=severity,
            title=title,
            description=description,
            event_data=event_data or {},
            indicators=indicators or {},
            targets=targets or {},
            created_at=datetime.utcnow(),
        )
        db.session.add(event)
        db.session.commit()
        return event

    def export_events(self, event_ids: list[int] | None = None, batch_size: int = 100) -> dict[str, Any]:
        """Экспортирует события во все активные SIEM-системы."""
        if not self.clients:
            logger.warning("No active SIEM clients configured")
            return {"status": "no_clients"}

        query = SIEMEvent.query.filter_by(sent_status="pending")
        if event_ids:
            query = query.filter(SIEMEvent.id.in_(event_ids))
        events = query.limit(batch_size).all()

        if not events:
            return {"status": "no_events"}

        results: dict[str, Any] = {}
        for client_id, client in self.clients.items():
            client_results = []
            for i in range(0, len(events), 100):
                batch = events[i : i + 100]
                if isinstance(client, SplunkClient):
                    result = client.send_batch_hec(batch)
                elif isinstance(client, ElasticClient):
                    result = client.bulk_index(batch)
                else:
                    result = {"success": False, "error": "Unknown client"}
                client_results.append(result)

            if all(r.get("success", False) for r in client_results):
                for event in events:
                    event.sent_at = datetime.utcnow()
                    event.sent_status = "sent"
                db.session.commit()
                results[f"client_{client_id}"] = {"status": "success", "count": len(events)}
            else:
                for event in events:
                    event.retry_count += 1
                    if event.retry_count >= 3:
                        event.sent_status = "failed"
                db.session.commit()
                results[f"client_{client_id}"] = {"status": "partial", "errors": client_results}

        return results

    def retry_failed(self, max_retries: int = 3) -> int:
        """Повторяет отправку неудавшихся событий."""
        failed = SIEMEvent.query.filter(
            SIEMEvent.sent_status == "failed",
            SIEMEvent.retry_count < max_retries,
        ).all()

        if failed:
            export_results = self.export_events([e.id for e in failed])
            return sum(v.get("count", 0) for v in export_results.values() if isinstance(v, dict))
        return 0

    def cleanup_old_events(self, days: int = 30) -> int:
        """Удаляет старые отправленные события."""
        cutoff = datetime.utcnow() - timedelta(days=days)
        deleted = SIEMEvent.query.filter(
            SIEMEvent.sent_status == "sent",
            SIEMEvent.sent_at < cutoff,
        ).delete()
        db.session.commit()
        return int(deleted or 0)
