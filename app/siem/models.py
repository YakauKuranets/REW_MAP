# -*- coding: utf-8 -*-
"""
Модели данных для экспорта в SIEM системы.
Соответствуют стандартным форматам ECS (Elastic Common Schema) и CEF (Common Event Format).
"""

from datetime import datetime
from enum import Enum

from app.extensions import db


class EventSeverity(Enum):
    """Уровни критичности событий по стандарту Syslog."""

    EMERGENCY = 0
    ALERT = 1
    CRITICAL = 2
    ERROR = 3
    WARNING = 4
    NOTICE = 5
    INFO = 6
    DEBUG = 7


class EventCategory(Enum):
    """Категории событий по ECS."""

    AUTHENTICATION = "authentication"
    INTRUSION_DETECTION = "intrusion_detection"
    THREAT_INTEL = "threat_intel"
    MALWARE = "malware"
    NETWORK = "network"
    DATABASE = "database"
    APPLICATION = "application"
    WEB = "web"


class SIEMEvent(db.Model):
    """Модель для хранения событий, ожидающих отправки в SIEM."""

    __tablename__ = "siem_events"

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.String(64), unique=True)
    source = db.Column(db.String(100))
    category = db.Column(db.String(50))
    severity = db.Column(db.Integer, default=EventSeverity.INFO.value)
    title = db.Column(db.String(255))
    description = db.Column(db.Text)
    event_data = db.Column(db.JSON)
    indicators = db.Column(db.JSON)
    targets = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    sent_at = db.Column(db.DateTime)
    sent_status = db.Column(db.String(20), default="pending")
    retry_count = db.Column(db.Integer, default=0)


class SIEMExportConfig(db.Model):
    """Конфигурация экспорта в SIEM системы."""

    __tablename__ = "siem_export_config"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    siem_type = db.Column(db.String(20))
    endpoint = db.Column(db.String(255))
    auth_token = db.Column(db.String(255))
    index_name = db.Column(db.String(100))
    hec_token = db.Column(db.String(255))
    ssl_verify = db.Column(db.Boolean, default=True)
    is_active = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
