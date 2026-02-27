"""
Модуль для работы с файлами данных (адреса, ожидающие заявки, история).

Вместо базы данных адреса хранятся в JSON-файле. Ожидающие заявки
(`pending markers`) и история их обработки также сохраняются в
файлах. Эти функции используются маршрутизаторами для загрузки и
сохранения данных.
"""

import json
import os
from typing import Any, Dict, List, Optional, Tuple

from compat_flask import current_app


def load_addresses() -> Tuple[List[Dict[str, Any]], int]:
    """
    Загрузить адреса из файла. Возвращает кортеж (список, next_id).

    Если файл отсутствует или повреждён, возвращается пустой список и
    начальный идентификатор 1.
    """
    path = current_app.config.get("ADDRESS_FILE")
    items: List[Dict[str, Any]] = []
    next_id = 1
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            if isinstance(data, list):
                items = data
                max_id = 0
                for it in items:
                    try:
                        max_id = max(max_id, int(it.get("id", 0)))
                    except Exception:
                        pass
                next_id = max_id + 1
    except FileNotFoundError:
        items = []
        next_id = 1
    except Exception:
        items = []
        next_id = 1
    return items, next_id


def save_addresses(items: List[Dict[str, Any]]) -> None:
    """Сохранить список адресов в файл."""
    path = current_app.config.get("ADDRESS_FILE")
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(items, fh, ensure_ascii=False, indent=2)
    except Exception:
        pass


def load_pending() -> Tuple[List[Dict[str, Any]], int]:
    """
    Загрузить ожидающие заявки из файла. Возвращает список и следующее id.
    """
    path = current_app.config.get("PENDING_FILE")
    markers: List[Dict[str, Any]] = []
    next_id = 1
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            if isinstance(data, list):
                markers = data
                max_id = 0
                for it in markers:
                    try:
                        max_id = max(max_id, int(it.get("id", 0)))
                    except Exception:
                        pass
                next_id = max_id + 1
    except FileNotFoundError:
        markers = []
        next_id = 1
    except Exception:
        markers = []
        next_id = 1
    return markers, next_id


def save_pending(markers: List[Dict[str, Any]]) -> None:
    """Сохранить ожидающие заявки в файл."""
    path = current_app.config.get("PENDING_FILE")
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(markers, fh, ensure_ascii=False, indent=2)
    except Exception:
        pass


def load_pending_history() -> Dict[str, Any]:
    """Загрузить историю обработки заявок из JSON-файла."""
    path = current_app.config.get("PENDING_HISTORY_FILE")
    history: Dict[str, Any] = {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            if isinstance(data, dict):
                history = data
    except Exception:
        history = {}
    return history


def save_pending_history(history: Dict[str, Any]) -> None:
    """Сохранить историю обработки заявок."""
    path = current_app.config.get("PENDING_HISTORY_FILE")
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(history, fh, ensure_ascii=False, indent=2)
    except Exception:
        pass
