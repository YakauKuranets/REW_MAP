"""Сервис постановки голосовых инцидентов в Celery-очередь."""

from __future__ import annotations

import os
import tempfile
from typing import Any

from compat_werkzeug_datastructures import FileStorage

from ..tasks import process_voice_incident


def enqueue_voice_incident(audio_file: FileStorage, agent_id: int) -> dict[str, Any]:
    """Сохранить входящее аудио во временный файл и отправить задачу в Celery."""
    suffix = ".ogg"
    filename = (audio_file.filename or "").lower()
    if "." in filename:
        suffix = "." + filename.rsplit(".", 1)[1]

    temp_dir = os.path.join(tempfile.gettempdir(), "mapv12_voice")
    os.makedirs(temp_dir, exist_ok=True)

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False, dir=temp_dir) as tmp:
        audio_file.save(tmp)
        path = tmp.name

    task = process_voice_incident.delay(path, int(agent_id))
    return {"status": "processing", "task_id": task.id}
