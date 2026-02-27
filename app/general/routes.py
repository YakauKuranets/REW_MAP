"""Маршруты общего назначения (импорт/экспорт).

Эти функции служат для поддержки старых URL `/api/export` и
`/api/import` и делегируют собственно работу сервисному слою.
"""

from __future__ import annotations

from compat_flask import Response, jsonify, request

from . import bp
from ..helpers import require_admin
from ..services.general_service import export_addresses_root as svc_export_root, import_addresses_root as svc_import_root


@bp.get('/export')
def export_addresses_root() -> Response:
    """Экспортировать список адресов в формате CSV (старый маршрут)."""
    csv_data = svc_export_root()
    return Response(
        csv_data,
        mimetype='text/csv; charset=utf-8',
        headers={
            'Content-Disposition': 'attachment; filename="addresses.csv"',
        },
    )


@bp.post('/import')
def import_addresses_root() -> Response:
    """Импортировать адреса из загруженного CSV‑файла (старый маршрут)."""
    require_admin()
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if not file or not file.filename:
        return jsonify({'error': 'No selected file'}), 400

    try:
        result = svc_import_root(file)
        return jsonify(result), 200
    except Exception as e:  # pragma: no cover - защитный слой
        return jsonify({'error': str(e)}), 500
