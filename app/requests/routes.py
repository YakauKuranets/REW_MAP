"""Маршруты для списка заявок (requests) в административном интерфейсе.

Используются для работы колокольчика: быстрый подсчёт количества
заявок, список для выпадающего меню и операции над отдельной заявкой.
Вся тяжёлая логика вынесена в :mod:`app.services.requests_service`.
"""

from __future__ import annotations

from compat_flask import Response, jsonify

from ..helpers import require_admin
from ..services.requests_service import (
    get_requests_count,
    list_pending_for_menu,
    get_request_details,
    delete_request,
)
from . import bp


@bp.get('/count')
def requests_count() -> Response:
    """Вернуть количество ожидающих заявок (только администратор)."""
    require_admin("viewer")
    count = get_requests_count()
    return jsonify({'count': count}), 200


@bp.get('/pending')
def list_pending_requests() -> Response:
    """Вернуть все pending‑заявки для отображения в меню."""
    require_admin("viewer")
    markers = list_pending_for_menu()
    return jsonify(markers), 200


@bp.get('/<int:req_id>')
def get_pending_request(req_id: int) -> Response:
    """Вернуть подробную информацию по заявке."""
    require_admin("viewer")
    details = get_request_details(req_id)
    if not details:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(details), 200


@bp.delete('/<int:req_id>')
def delete_pending_request(req_id: int) -> Response:
    """Удалить заявку из очереди (только администратор)."""
    require_admin()
    result = delete_request(req_id)
    return jsonify(result), 200