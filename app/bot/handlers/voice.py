"""Voice handlers for async Celery dispatch."""

from __future__ import annotations

import os
import tempfile

from aiogram import F, Router
from aiogram.types import Message

from ...tasks import process_voice_incident

router = Router(name="voice")


@router.message(F.voice)
async def handle_voice_message(message: Message) -> None:
    """Download OGG voice message, enqueue Celery task and reply immediately."""
    if not message.voice or not message.from_user:
        await message.answer("Не удалось обработать аудио. Попробуйте отправить снова.")
        return

    temp_dir = os.path.join(tempfile.gettempdir(), "mapv12_voice")
    os.makedirs(temp_dir, exist_ok=True)

    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False, dir=temp_dir) as tmp_file:
        local_path = tmp_file.name

    file_info = await message.bot.get_file(message.voice.file_id)
    await message.bot.download_file(file_info.file_path, destination=local_path)

    process_voice_incident.delay(local_path, int(message.from_user.id))

    await message.answer("🎙 Аудио получено, ИИ-диспетчер расшифровывает координаты...")
