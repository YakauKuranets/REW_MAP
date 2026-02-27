# -*- coding: utf-8 -*-
"""Face similarity helper for lawful OSINT correlation workflows."""

from __future__ import annotations

import logging

import face_recognition

logger = logging.getLogger(__name__)


def compare_faces(known_image_path: str, unknown_image_path: str) -> float:
    """Compares faces from two images and returns a similarity percentage (0..100)."""
    logger.info("[BIOMETRICS] Starting facial comparison via dlib/ResNet encodings")
    try:
        known_image = face_recognition.load_image_file(known_image_path)
        unknown_image = face_recognition.load_image_file(unknown_image_path)

        known_encodings = face_recognition.face_encodings(known_image)
        unknown_encodings = face_recognition.face_encodings(unknown_image)

        if not known_encodings or not unknown_encodings:
            return 0.0

        match_distance = face_recognition.face_distance([known_encodings[0]], unknown_encodings[0])[0]
        similarity = max(0.0, 100.0 - (match_distance * 100.0))
        return round(similarity, 2)
    except Exception as exc:
        logger.error("[BIOMETRICS] Analysis error: %s", exc)
        return 0.0
