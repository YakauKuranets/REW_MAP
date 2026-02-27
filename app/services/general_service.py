"""Сервис общего назначения (обёртка над импортом/экспортом).

Содержит функции для старых маршрутов `/api/export` и `/api/import`,
делегируя собственно логику модулю :mod:`app.services.addresses_service`.
"""

from __future__ import annotations

from io import StringIO
from typing import Dict, Any

from .addresses_service import export_addresses_csv, import_addresses_from_csv


def export_addresses_root() -> str:
    """Вернуть CSV‑строку экспорта адресов для старого маршрута `/api/export`."""
    return export_addresses_csv()


def import_addresses_root(file_storage) -> Dict[str, Any]:
    """Импортировать адреса из загруженного файла для `/api/import`."""
    stream = StringIO(file_storage.stream.read().decode('utf-8'))
    return import_addresses_from_csv(stream)
