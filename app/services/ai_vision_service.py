"""AI vision service for incident photo auto-tagging."""

from __future__ import annotations

import os
from typing import Dict, List


def _heuristic_tags(image_path: str) -> Dict[str, object]:
    name = os.path.basename(image_path).lower()
    tags: List[str] = []
    category = "general"
    priority = 2

    if any(k in name for k in ("fire", "burn", "smoke", "flame")):
        tags.extend(["fire"])
        category = "fire"
        priority = max(priority, 5)
    if any(k in name for k in ("weapon", "gun", "knife")):
        tags.extend(["weapon"])
        category = "security"
        priority = max(priority, 5)
    if any(k in name for k in ("crash", "accident", "car")):
        tags.extend(["car", "crash"])
        category = "traffic"
        priority = max(priority, 4)

    if not tags:
        tags = ["unclassified"]

    return {"category": category, "tags": sorted(set(tags)), "priority": int(priority)}


def analyze_incident_photo(image_path: str) -> dict:
    """Analyze incident photo and return category/tags/priority payload.

    For this phase, service supports env-driven provider selection.
    If external provider is not configured, heuristic fallback is used.
    """
    provider = (os.getenv("AI_VISION_PROVIDER") or "heuristic").strip().lower()

    if provider in {"heuristic", "mock", ""}:
        return _heuristic_tags(image_path)

    # External providers can be integrated here (OpenAI/Ollama), keeping stable contract.
    return _heuristic_tags(image_path)
