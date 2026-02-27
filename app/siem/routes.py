# -*- coding: utf-8 -*-
"""
API для управления экспортом в SIEM системы.
"""

from datetime import datetime, timedelta
import logging

from flask import Blueprint, request, jsonify

from app.auth.decorators import jwt_or_api_required
from app.siem.models import SIEMEvent, SIEMExportConfig, db
from app.siem.exporter import SIEMExporter

logger = logging.getLogger(__name__)
siem_bp = Blueprint('siem', __name__, url_prefix='/siem')


@siem_bp.route('/config', methods=['GET'])
@jwt_or_api_required
def list_configs():
    """Возвращает список конфигураций SIEM."""
    configs = SIEMExportConfig.query.all()
    return jsonify([{
        'id': c.id,
        'name': c.name,
        'siem_type': c.siem_type,
        'endpoint': c.endpoint,
        'index_name': c.index_name,
        'is_active': c.is_active
    } for c in configs])


@siem_bp.route('/config', methods=['POST'])
@jwt_or_api_required
def create_config():
    """Создаёт новую конфигурацию SIEM."""
    data = request.json or {}
    config = SIEMExportConfig(
        name=data.get('name'),
        siem_type=data.get('siem_type'),
        endpoint=data.get('endpoint'),
        auth_token=data.get('auth_token'),
        index_name=data.get('index_name'),
        hec_token=data.get('hec_token'),
        ssl_verify=data.get('ssl_verify', True),
        is_active=data.get('is_active', False)
    )
    db.session.add(config)
    db.session.commit()
    return jsonify({'id': config.id, 'status': 'created'})


@siem_bp.route('/config/<int:config_id>/test', methods=['POST'])
@jwt_or_api_required
def test_config(config_id):
    """Тестирует соединение с SIEM."""
    config = SIEMExportConfig.query.get(config_id)
    if not config:
        return jsonify({'error': 'Config not found'}), 404

    exporter = SIEMExporter()
    test_event = exporter.create_event(
        source='test',
        category='test',
        title='Test Event',
        description='This is a test event from X-GEN platform',
        severity=6
    )

    result = exporter.export_events([test_event.id])
    return jsonify(result)


@siem_bp.route('/events/pending', methods=['GET'])
@jwt_or_api_required
def get_pending_events():
    """Возвращает список ожидающих отправки событий."""
    events = SIEMEvent.query.filter_by(sent_status='pending').order_by(SIEMEvent.created_at.desc()).limit(100).all()
    return jsonify([{
        'id': e.id,
        'event_id': e.event_id,
        'source': e.source,
        'title': e.title,
        'severity': e.severity,
        'created_at': e.created_at.isoformat() if e.created_at else None
    } for e in events])


@siem_bp.route('/export', methods=['POST'])
@jwt_or_api_required
def trigger_export():
    """Запускает экспорт ожидающих событий."""
    exporter = SIEMExporter()
    result = exporter.export_events()
    return jsonify(result)


@siem_bp.route('/stats', methods=['GET'])
@jwt_or_api_required
def get_stats():
    """Возвращает статистику по экспорту."""
    pending = SIEMEvent.query.filter_by(sent_status='pending').count()
    sent_last_24h = SIEMEvent.query.filter(
        SIEMEvent.sent_status == 'sent',
        SIEMEvent.sent_at >= datetime.utcnow() - timedelta(days=1)
    ).count()
    failed = SIEMEvent.query.filter_by(sent_status='failed').count()

    return jsonify({
        'pending': pending,
        'sent_last_24h': sent_last_24h,
        'failed': failed,
        'total': pending + sent_last_24h + failed
    })
