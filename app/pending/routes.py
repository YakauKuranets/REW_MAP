"""Маршруты для работы с очередью заявок (pending markers).

Вся тяжёлая логика перенесена в :mod:`app.services.pending_service`,
здесь остаются только проверки прав и HTTP-обёртки.
"""

from __future__ import annotations

import os
import time
import json
from compat_flask import Response, jsonify, request, current_app
from compat_werkzeug_utils import secure_filename

from ..helpers import require_admin, get_current_admin
from ..services.permissions_service import has_zone_access
from ..services.pending_service import (
    get_pending_count,
    list_pending_markers,
    approve_pending,
    reject_pending,
    clear_all_pending,
)
from ..models import PendingMarker
from ..extensions import db
from ..sockets import broadcast_event_sync
from . import bp

ALLOWED_AR_EXTENSIONS = {'ply', 'obj'}

def allowed_ar_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_AR_EXTENSIONS


@bp.get('/count')
def pending_count() -> Response:
    """Публичный счётчик ожидающих заявок."""
    count = get_pending_count()
    return jsonify({'count': count})


@bp.get('')
def list_pending() -> Response:
    """Список ожидающих заявок (только для администратора).

    Если у администратора привязаны зоны, показываем только те
    заявки, у которых либо нет zone_id, либо zone_id входит в
    доступные зоны. superadmin видит все заявки.
    """
    require_admin("viewer")
    markers = list_pending_markers()

    admin = get_current_admin()
    if not admin:
        return jsonify(markers)

    filtered = []
    for m in markers:
        zid = m.get('zone_id')
        # Заявки без зоны видны всем, заявки с зоной — только тем,
        # у кого есть доступ к этой зоне (или superadmin).
        if zid is None or has_zone_access(admin, zid):
            filtered.append(m)

    return jsonify(filtered)


@bp.post('/<int:pid>/approve')
def pending_approve(pid: int) -> Response:
    """Одобрить заявку и перенести её в список адресов.

    Перед одобрением проверяем, что у администратора есть доступ
    к зоне заявки (если она указана). superadmin может одобрять
    любые заявки.
    """
    require_admin()
    pending = PendingMarker.query.get(pid)
    if not pending:
        return jsonify({'error': 'not found'}), 404

    if pending.zone_id is not None:
        admin = get_current_admin()
        if admin is None or not has_zone_access(admin, pending.zone_id):
            return jsonify({'error': 'forbidden'}), 403

    try:
        result = approve_pending(pid)
    except ValueError:
        return jsonify({'error': 'not found'}), 404
    return jsonify(result)


@bp.post('/<int:pid>/reject')
def pending_reject(pid: int) -> Response:
    """Отклонить заявку. Просто удалить её из очереди.

    Проверяем доступ администратора к зоне заявки (если указана).
    """
    require_admin()
    pending = PendingMarker.query.get(pid)
    if not pending:
        return jsonify({'error': 'not found'}), 404

    if pending.zone_id is not None:
        admin = get_current_admin()
        if admin is None or not has_zone_access(admin, pending.zone_id):
            return jsonify({'error': 'forbidden'}), 403

    try:
        result = reject_pending(pid)
    except ValueError:
        return jsonify({'error': 'not found'}), 404
    return jsonify(result)


@bp.post('/clear')
def pending_clear() -> Response:
    """Очистить очередь ожидания. Устанавливает статус cancelled для всех.

    Эта операция затрагивает все заявки во всех зонах, поэтому
    доступна только супер‑администратору.
    """
    require_admin(min_role="superadmin")
    result = clear_all_pending()
    return jsonify(result)


@bp.post('/<int:pid>/ar_scan')
def upload_ar_scan(pid: int) -> Response:
    """Принимает 3D-облако точек (Point Cloud) с Android-устройства
    и прикрепляет его к заявке.
    """
    marker = db.session.get(PendingMarker, pid)
    if not marker:
        return jsonify({"error": "Заявка не найдена"}), 404

    if 'file' not in request.files:
        return jsonify({"error": "Файл не передан"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "Файл пуст"}), 400

    if file and file.filename and allowed_ar_file(file.filename):
        # Генерируем безопасное имя файла
        filename = secure_filename(f"ar_scan_m{pid}_{int(time.time())}.ply")

        # Убедимся, что папка uploads существует (в папке static)
        upload_folder = os.path.join(current_app.root_path, '..', 'static', 'uploads', 'ar_scans')
        os.makedirs(upload_folder, exist_ok=True)

        filepath = os.path.join(upload_folder, filename)
        file.save(filepath)

        # Сохраняем ссылку в базу (в JSON-поле details)
        details = {}
        if marker.details:
            try:
                details = json.loads(marker.details) if isinstance(marker.details, str) else marker.details
            except Exception:
                pass

        details['ar_scan_url'] = f"/static/uploads/ar_scans/{filename}"

        # Дампим обратно в строку
        marker.details = json.dumps(details, ensure_ascii=False)
        db.session.commit()

        # Кидаем уведомление в WebSockets, чтобы 3D-карта сразу подгрузила модель
        try:
            broadcast_event_sync('ar_scan_uploaded', {
                'marker_id': pid,
                'ar_scan_url': details['ar_scan_url']
            })
        except Exception:
            pass # Игнорим ошибку сокетов (best-effort)

        return jsonify({"status": "ok", "url": details['ar_scan_url']}), 200

    return jsonify({"error": "Неверный формат файла. Разрешены только .ply и .obj"}), 400