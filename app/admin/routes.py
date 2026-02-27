"""
Администраторские маршруты для телеграм‑бота и панели.

В этих обработчиках собирается статистика по заявкам и адресам,
возвращается список адресов с пагинацией и список заявок (pending
и история) по статусу. Эти маршруты носят информационный
характер и не требуют авторизации, так как подразумевается, что
доступ к ним осуществляется через отдельный бот, который
выполняет проверку прав на своей стороне.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List

from flask import request, jsonify

from ..extensions import db
from ..models import Address, PendingMarker, PendingHistory

from . import bp


@bp.get('/summary')
def admin_summary():
    """Вернуть краткую статистику по заявкам и адресам.

    Формат ответа совместим с предыдущей реализацией:
    {
      "applications": {
        "active": <int>,       # количество ожидающих заявок
        "approved": <int>,     # количество одобренных заявок (всего)
        "rejected": <int>,     # количество отклонённых заявок (всего)
        "new_last_7d": <int>,  # количество новых адресов за последние 7 дней
      },
      "addresses": {
        "total": <int>         # всего адресов в базе
      }
    }
    """
    # Количество ожидающих заявок (pending)
    active = PendingMarker.query.count()
    # Количество одобренных заявок — считаем записи истории со статусом 'approved'
    approved = PendingHistory.query.filter(PendingHistory.status == 'approved').count()
    # Количество отклонённых заявок — считаем записи истории со статусом 'rejected'
    rejected = PendingHistory.query.filter(PendingHistory.status == 'rejected').count()
    # Количество новых адресов за последние 7 дней
    cutoff = datetime.utcnow() - timedelta(days=7)
    new_last_7d = Address.query.filter(Address.created_at >= cutoff).count()
    # Общее количество адресов
    total_addresses = Address.query.count()
    return jsonify({
        'applications': {
            'active': active,
            'approved': approved,
            'rejected': rejected,
            'new_last_7d': new_last_7d,
        },
        'addresses': {
            'total': total_addresses,
        }
    })


@bp.get('/addresses')
def admin_addresses():
    """Вернуть список адресов с пагинацией.

    Параметры запроса:
    - page: номер страницы (по умолчанию 1)
    - limit: количество элементов на странице (по умолчанию 10)

    Формат ответа:
    {
      "items": [<address_dict>, ...],
      "total": <int>
    }
    """
    try:
        page = int(request.args.get('page', 1))
    except Exception:
        page = 1
    try:
        limit = int(request.args.get('limit', 10))
    except Exception:
        limit = 10
    page = max(1, page)
    limit = max(1, limit)
    query = Address.query
    total = query.count()
    items = query.order_by(Address.id.desc()).offset((page - 1) * limit).limit(limit).all()
    return jsonify({
        'items': [addr.to_dict() for addr in items],
        'total': total
    })


@bp.get('/applications')
def admin_applications():
    """Вернуть список заявок или записей истории по статусу.

    Параметры запроса:
    - status: pending | approved | rejected
    - limit: максимальное количество элементов (по умолчанию 10)

    Формат ответа:
    {
      "applications": [ { ... }, ... ],
      "total": <int>
    }
    Где каждый элемент в списке содержит по крайней мере id, status и имя,
    если оно доступно. Для одобренных заявок возвращается также address_id,
    для отклонённых — причина отсутствует (отсутствует или None).
    """
    status = request.args.get('status', 'pending').strip().lower()
    try:
        limit = int(request.args.get('limit', 10))
    except Exception:
        limit = 10
    limit = max(1, limit)
    # pending: возврат всех ожидающих заявок
    if status == 'pending':
        query = PendingMarker.query.order_by(PendingMarker.id.desc())
        total = query.count()
        markers = query.limit(limit).all()
        items: List[Dict[str, Any]] = []
        for p in markers:
            items.append(p.to_dict())
        return jsonify({
            'applications': items,
            'total': total
        })
    # approved or rejected: читаем историю
    hist_query = PendingHistory.query.filter(PendingHistory.status == status).order_by(PendingHistory.id.desc())
    total = hist_query.count()
    hist_items = hist_query.limit(limit).all()
    out: List[Dict[str, Any]] = []
    for rec in hist_items:
        item: Dict[str, Any] = {
            'id': rec.pending_id,
            'status': rec.status,
            'timestamp': rec.timestamp.isoformat() if rec.timestamp else None,
        }
        # Для одобренных заявок пытаемся получить данные адреса
        if rec.status == 'approved' and rec.address_id:
            addr = Address.query.get(rec.address_id)
            if addr:
                item['name'] = addr.name
                item['lat'] = addr.lat
                item['lon'] = addr.lon
                item['category'] = addr.category
                item['link'] = addr.link
                item['notes'] = addr.notes
                item['address_id'] = addr.id
        out.append(item)
    return jsonify({
        'applications': out,
        'total': total
    })


@bp.get('/applications/<int:pid>')
def admin_application_detail(pid: int):
    """Вернуть подробную информацию о заявке или истории по её ID.

    Для pending‑заявок возвращается структура PendingMarker.to_dict().
    Для записей истории пытаемся вернуть информацию об адресе, если
    заявка была одобрена. В других случаях возвращается только id и
    статус.
    """
    # Проверяем, есть ли заявка в очереди (pending)
    pm = PendingMarker.query.get(pid)
    if pm:
        return jsonify(pm.to_dict())
    # Ищем запись в истории
    hist = PendingHistory.query.filter(PendingHistory.pending_id == pid).order_by(PendingHistory.id.desc()).first()
    if not hist:
        return jsonify({'error': 'not found'}), 404
    item: Dict[str, Any] = {
        'id': hist.pending_id,
        'status': hist.status,
        'timestamp': hist.timestamp.isoformat() if hist.timestamp else None,
    }
    # Если заявка была одобрена, пытаемся вернуть адрес
    if hist.status == 'approved' and hist.address_id:
        addr = Address.query.get(hist.address_id)
        if addr:
            item['address'] = addr.to_dict()
    return jsonify(item)