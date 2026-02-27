# -*- coding: utf-8 -*-
"""Audit API (superadmin) и запуск диагностических задач."""

from __future__ import annotations

import logging

from compat_flask import Blueprint, jsonify, request

from ..helpers import require_admin
from ..models import AdminAuditLog
from ..tasks.diagnostics_tasks import run_security_scan

bp = Blueprint('audit', __name__)
logger = logging.getLogger(__name__)


@bp.get('/')
def list_audit():
    require_admin(min_role='superadmin')
    try:
        limit = int(request.args.get('limit') or 200)
    except Exception:
        limit = 200
    limit = max(1, min(limit, 500))
    try:
        offset = int(request.args.get('offset') or 0)
    except Exception:
        offset = 0
    offset = max(0, offset)

    action = (request.args.get('action') or '').strip() or None
    actor = (request.args.get('actor') or '').strip() or None

    q = AdminAuditLog.query
    if action:
        q = q.filter(AdminAuditLog.action == action)
    if actor:
        q = q.filter(AdminAuditLog.actor == actor)

    rows = q.order_by(AdminAuditLog.ts.desc()).offset(offset).limit(limit).all()
    return jsonify([r.to_dict() for r in rows]), 200


@bp.post('/start')
def start_security_scan():
    """
    Запускает выбранный профиль диагностики для указанной цели.
    Все операции выполняются в рамках authorised тестирования.
    """
    require_admin(min_role='superadmin')
    payload = request.get_json(silent=True) or {}

    target = (payload.get('target') or '').strip()
    profile = (payload.get('scan_profile') or '').strip().upper()
    use_proxy = bool(payload.get('use_proxy', True))

    allowed_profiles = {'WEB_DIR_SCAN', 'PORT_SCAN', 'OSINT_DEEP'}
    if not target:
        return jsonify(error='target is required'), 400
    if profile not in allowed_profiles:
        return jsonify(error='scan_profile is invalid'), 400

    logger.info('Запуск диагностики для цели %s, профиль %s, прокси=%s', target, profile, use_proxy)
    task = run_security_scan.delay(None, target, profile, use_proxy, None)

    return jsonify(
        {
            'status': 'accepted',
            'task_id': task.id,
            'target': target,
            'profile': profile,
            'message': "Диагностика запущена. Результаты появятся в разделе 'Результаты'.",
        }
    ), 202
