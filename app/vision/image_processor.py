# -*- coding: utf-8 -*-
"""
Модуль для обработки изображений с использованием нейросетевых моделей.
Тяжёлые вычисления вынесены в пул потоков, чтобы не блокировать асинхронный event loop.
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

import face_recognition

logger = logging.getLogger(__name__)

# Пул потоков для CPU-интенсивных операций
image_executor = ThreadPoolExecutor(max_workers=2)


def _compare_images_sync(image1_path: str, image2_path: str) -> float:
    """
    Синхронная функция сравнения двух изображений (например, по лицам).
    Выполняется в отдельном потоке.
    """
    try:
        img1 = face_recognition.load_image_file(image1_path)
        img2 = face_recognition.load_image_file(image2_path)

        enc1 = face_recognition.face_encodings(img1)
        enc2 = face_recognition.face_encodings(img2)

        if not enc1 or not enc2:
            return 0.0

        distance = face_recognition.face_distance([enc1[0]], enc2[0])[0]
        similarity = max(0.0, 100.0 - (distance * 100.0))
        return round(similarity, 2)
    except Exception as exc:
        logger.error("[IMAGE_PROCESSOR] Ошибка сравнения: %s", exc)
        return 0.0


async def compare_images_async(image1_path: str, image2_path: str) -> float:
    """
    Асинхронная обёртка для сравнения изображений.
    Задача отправляется в пул потоков, освобождая event loop.
    """
    logger.info("[IMAGE_PROCESSOR] Отправка задачи в пул потоков...")
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        image_executor,
        _compare_images_sync,
        image1_path,
        image2_path,
    )
    return result
