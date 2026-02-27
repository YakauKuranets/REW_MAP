"""Сервисный слой для административного списка заявок (колокольчик).

Логика здесь работает поверх моделей PendingMarker и Address,
обеспечивая подсчёт, представление и удаление заявок.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import func

from ..extensions import db
from ..models import PendingMarker, Address


def get_requests_count() -> int:
    """Вернуть количество заявок в очереди (PendingMarker)."""
    return PendingMarker.query.count()



def list_pending_for_menu() -> List[Dict[str, Any]]:
    """Вернуть список заявок для отображения в меню колокольчика.

    Заявки отсортированы от новых к старым.
    """
    markers = PendingMarker.query.order_by(
        PendingMarker.created_at.desc(), PendingMarker.id.desc()
    ).all()
    payload: List[Dict[str, Any]] = []
    for p in markers:
        payload.append(
            {
                "id": p.id,
                "name": p.name or "",
                "address": p.name or "",
                "lat": p.lat,
                "lon": p.lon,
                "description": p.notes or "",
                "notes": p.notes or "",
                "status": p.status or "",
                "link": p.link or "",
                "category": p.category or "",
                "reporter": p.reporter or {},
                "photo": p.photo,
            }
        )
    return payload


def get_request_details(req_id: int) -> Optional[Dict[str, Any]]:
    """Вернуть подробную информацию о заявке или None, если она не найдена."""
    p = PendingMarker.query.get(req_id)
    if not p:
        return None
    return {
        "id": p.id,
        "name": p.name or "",
        "address": p.name or "",
        "lat": p.lat,
        "lon": p.lon,
        "description": p.notes or "",
        "notes": p.notes or "",
        "status": p.status or "",
        "link": p.link or "",
        "category": p.category or "",
        "reporter": p.reporter or {},
        "photo": p.photo,
    }


def delete_request(req_id: int) -> Dict[str, Any]:
    """Удалить заявку вместе с обработкой прикреплённой фотографии.

    Если к заявке прикреплена фотография, сервис попытается
    перенести её к существующему адресу с совпадающими координатами
    или названием. Возвращает словарь с полями:

    - ``status`` — строка статуса;
    - ``deleted`` — булево значение.
    """
    p = PendingMarker.query.get(req_id)
    if not p:
        return {"status": "ok", "deleted": False}

    photo = p.photo
    name = (p.name or "").strip().lower()
    lat = p.lat
    lon = p.lon

    # Попытка привязать фото к существующему адресу
    if photo:
        target: Optional[Address] = None

        # Сначала ищем по точным координатам (если заданы)
        if lat is not None and lon is not None:
            target = (
                Address.query.filter_by(lat=lat, lon=lon)
                .order_by(Address.id.desc())
                .first()
            )

        # Если по координатам не нашли — ищем по имени (без учёта регистра)
        if not target and name:
            target = (
                Address.query
                .filter(func.lower(Address.name) == name)
                .order_by(Address.id.desc())
                .first()
            )

        if target and not target.photo:
            target.photo = photo

    db.session.delete(p)
    db.session.commit()
    return {"status": "ok", "deleted": True}

