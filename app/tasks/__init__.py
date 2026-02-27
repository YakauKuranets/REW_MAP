"""Celery-задачи приложения."""

from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI

from app.extensions import celery_app, db
from app.models import PendingMarker
from app.realtime.broker import get_broker
from app.alerting import checker as alerting_checker  # noqa: F401
from app.tasks import reports_delivery as reports_delivery_tasks  # noqa: F401
from app.tasks import diagnostics_scans as diagnostics_scans_tasks  # noqa: F401
from app.tasks import threat_intel_tasks as threat_intel_tasks  # noqa: F401
from app.tasks import siem_tasks as siem_tasks  # noqa: F401
from app.tasks import diagnostics_tasks as diagnostics_tasks  # noqa: F401
from app.tasks import ai_mutation_tasks as ai_mutation_tasks  # noqa: F401
from app.tasks import mutation_testing as mutation_testing_tasks  # noqa: F401
from app.tasks import operational_tasks as operational_tasks  # noqa: F401


@celery_app.task(bind=True)
def process_voice_incident(self, file_path: str, agent_id: int) -> dict[str, Any]:
    """Обработать голосовой инцидент в фоне (Whisper + GPT + DB + Redis push)."""
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    try:
        with open(file_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="ru",
            )

        text = (getattr(transcript, "text", "") or "").strip()
        if not text:
            raise ValueError("Не удалось распознать текст")

        system_prompt = """
        Ты — ИИ-диспетчер экстренной службы. Проанализируй текст инцидента.
        Твоя задача — вернуть СТРОГИЙ JSON без markdown разметки.
        Поля:
        - category: одна из [Пожар, ДТП, Инфраструктура, Другое]
        - address: извлеченный адрес или null, если не указан
        - description: краткое, четкое описание инцидента (максимум 2 предложения)
        """

        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Текст: {text}"},
            ],
            response_format={"type": "json_object"},
        )
        response_content = completion.choices[0].message.content
        parsed = json.loads(response_content)

        category = (parsed.get("category") or "Другое").strip()[:128]
        address = (parsed.get("address") or "").strip()
        description = (parsed.get("description") or text).strip()

        pending = PendingMarker(
            name=address or "Голосовой инцидент",
            notes=description,
            status="Новая",
            link="",
            category=category,
            user_id=str(agent_id),
            reporter=str(agent_id),
        )
        db.session.add(pending)
        db.session.commit()

        incident_payload = {
            "id": pending.id,
            "name": pending.name,
            "category": pending.category,
            "notes": pending.notes,
            "status": pending.status,
            "user_id": pending.user_id,
            "source": "voice_ai",
        }

        broker = get_broker()
        broker.publish_event("map_updates", {"type": "NEW_INCIDENT", "data": incident_payload})

        return {"ok": True, "incident_id": pending.id, "data": incident_payload}
    except Exception as exc:
        db.session.rollback()
        return {"ok": False, "error": str(exc)}
    finally:
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
        except Exception:
            pass
