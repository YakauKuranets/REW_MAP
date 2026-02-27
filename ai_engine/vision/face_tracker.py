"""Face comparison helpers for AI engine."""

from .image_processor import _compare_images_sync as compare_faces_sync
from .image_processor import compare_images_async as compare_faces_async

__all__ = ["compare_faces_sync", "compare_faces_async"]
