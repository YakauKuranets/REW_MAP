# -*- coding: utf-8 -*-
"""Backward-compatible wrapper over app.vision.image_processor."""

from app.vision.image_processor import compare_images_async
from app.vision.image_processor import _compare_images_sync as _compare_faces_sync


async def compare_faces_async(known_image_path: str, unknown_image_path: str) -> float:
    return await compare_images_async(known_image_path, unknown_image_path)


def compare_faces(known_image_path: str, unknown_image_path: str) -> float:
    return _compare_faces_sync(known_image_path, unknown_image_path)
