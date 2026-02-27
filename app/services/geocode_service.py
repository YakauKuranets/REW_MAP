"""Сервисный слой для геокодирования.

Содержит функцию :func:`geocode`, которая инкапсулирует логику
поиска в офлайн‑базе и обращения к сервису Nominatim.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import requests
from compat_flask import current_app


def _load_offline_entries() -> List[Dict[str, Any]]:
    path = current_app.config.get('OFFLINE_GEOCODE_FILE')
    if not path:
        return []
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
            if isinstance(data, list):
                return data
    except Exception:
        return []
    return []


def _search_offline(entries: List[Dict[str, Any]], q: str, limit: int) -> List[Dict[str, Any]]:
    q_norm = q.lower()
    results: List[Dict[str, Any]] = []
    for item in entries:
        try:
            name = (item.get('name') or item.get('display_name') or '').lower()
            if not name:
                continue
            if q_norm in name:
                results.append(
                    {
                        'display_name': item.get('display_name') or item.get('name'),
                        'lat': item.get('lat'),
                        'lon': item.get('lon'),
                    }
                )
                if len(results) >= limit:
                    break
        except Exception:
            continue
    return results


def _search_online(q: str, limit: int, lang: str = 'ru') -> List[Dict[str, Any]]:
    try:
        params = {'q': q, 'format': 'json', 'limit': limit, 'accept-language': lang}
        r = requests.get(
            'https://nominatim.openstreetmap.org/search',
            params=params,
            headers={'User-Agent': 'map-v12-geocode'},
            timeout=10,
        )
        if not r.ok:
            return []
        data = r.json()
        out: List[Dict[str, Any]] = []
        if isinstance(data, list):
            for item in data:
                out.append(
                    {
                        'display_name': item.get('display_name'),
                        'lat': item.get('lat'),
                        'lon': item.get('lon'),
                    }
                )
                if len(out) >= limit:
                    break
        return out
    except Exception:
        return []


def geocode(q: str, limit: int = 1, lang: str = 'ru') -> List[Dict[str, Any]]:
    """Выполнить геокодирование с использованием офлайн‑базы и Nominatim."""
    q = (q or '').strip()
    if not q:
        return []

    # Сначала офлайн
    offline_entries = _load_offline_entries()
    results = _search_offline(offline_entries, q, limit)
    if results:
        return results

    # Затем онлайн
    return _search_online(q, limit, lang=lang)
