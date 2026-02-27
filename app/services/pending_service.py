"""Сервисный слой для очереди заявок (pending markers).

Здесь размещается бизнес-логика работы с сущностями PendingMarker /
PendingHistory / Address. Маршруты в :mod:`app.pending.routes`
превращаются в тонкие HTTP-обёртки.
"""

from __future__ import annotations

from typing import Any, Dict, List

from ..extensions import db
from ..models import Address, PendingMarker, PendingHistory
from ..helpers import get_current_admin, ensure_zone_access
from ..realtime.broker import get_broker
from ..sockets import broadcast_event_sync


def get_pending_count() -> int:
    """Вернуть количество заявок в очереди."""
    return PendingMarker.query.count()


def list_pending_markers() -> List[Dict[str, Any]]:
    """Вернуть список ожидающих заявок как список словарей.

    Самые новые заявки идут первыми.
    С учётом зон доступа текущего администратора: superadmin
    видит все заявки, остальные — только по своим зонам.
    """
    query = PendingMarker.query
    admin = get_current_admin()
    if admin is not None and getattr(admin, 'role', None) != 'superadmin':
        zone_ids = [z.id for z in admin.zones]
        if zone_ids:
            query = query.filter(PendingMarker.zone_id.in_(zone_ids))
        else:
            query = query.filter(False)
    query = query.order_by(PendingMarker.created_at.desc(), PendingMarker.id.desc())
    return [p.to_dict() for p in query.all()]



def approve_pending(pid: int) -> Dict[str, Any]:
    """Одобрить заявку и перенести её в список адресов.

    Возвращает словарь с полями:
    - ``status`` — строка статуса;
    - ``id`` — идентификатор созданного адреса.

    Если заявка не найдена, возбуждается ValueError.
    """
    pending = PendingMarker.query.get(pid)
    if not pending:
        raise ValueError("pending_not_found")

    # Проверяем доступ к зоне заявки (если указана)
    if pending.zone_id is not None:
        ensure_zone_access(pending.zone_id)

    # Создаём новый адрес на основе заявки
    address = Address(
        name=pending.name,
        lat=pending.lat,
        lon=pending.lon,
        notes=pending.notes,
        status=pending.status,
        link=pending.link,
        category=pending.category,
        zone_id=pending.zone_id,
        photo=pending.photo,
    )
    db.session.add(address)

    # Создаём запись в истории
    hist = PendingHistory(
        pending_id=pending.id,
        status="approved",
        address_id=None,  # обновим после flush
    )
    db.session.add(hist)
    db.session.flush()
    hist.address_id = address.id

    # Удаляем сам pending
    db.session.delete(pending)
    db.session.commit()

    address_payload = address.to_dict()

    # уведомляем клиентов
    try:
        broadcast_event_sync(
            "pending_approved",
            {"pending_id": pid, "address_id": address.id},
        )
    except Exception:
        # логирование оставляем в маршруте/общем логере
        pass

    try:
        get_broker().publish_event(
            "map_updates",
            {
                "event": "MARKER_APPROVED",
                "marker_id": pid,
                "new_object": address_payload,
            },
        )
    except Exception:
        pass

    return {"status": "ok", "id": address.id}


def reject_pending(pid: int) -> Dict[str, Any]:
    """Отклонить заявку: перенести в историю и удалить.

    Возвращает словарь с полями:
    - ``status`` — строка статуса;
    - ``remaining`` — количество оставшихся заявок.
    """
    pending = PendingMarker.query.get(pid)
    if not pending:
        raise ValueError("pending_not_found")

    # Проверяем доступ к зоне заявки (если указана)
    if pending.zone_id is not None:
        ensure_zone_access(pending.zone_id)

    hist = PendingHistory(
        pending_id=pending.id,
        status="rejected",
    )
    db.session.add(hist)
    db.session.delete(pending)
    db.session.commit()

    remaining = PendingMarker.query.count()

    try:
        broadcast_event_sync(
            "pending_rejected",
            {"pending_id": pid, "remaining": remaining},
        )
    except Exception:
        pass

    try:
        get_broker().publish_event(
            "map_updates",
            {
                "event": "MARKER_REJECTED",
                "marker_id": pid,
            },
        )
    except Exception:
        pass

    return {"status": "ok", "remaining": remaining}


def clear_all_pending() -> Dict[str, Any]:
    """Очистить очередь ожидания.

    Все существующие PendingMarker переносятся в историю со
    статусом ``cancelled``, затем удаляются. В конце посылается
    событие ``pending_cleared``.
    """
    markers = PendingMarker.query.all()

    for p in markers:
        hist = PendingHistory(
            pending_id=p.id,
            status="cancelled",
        )
        db.session.add(hist)
        db.session.delete(p)

    db.session.commit()

    try:
        broadcast_event_sync("pending_cleared", {})
    except Exception:
        pass

    return {"status": "ok"}
