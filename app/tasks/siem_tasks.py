# -*- coding: utf-8 -*-
"""
Периодические задачи для автоматического экспорта событий в SIEM.
"""

import logging

from celery import shared_task

from app.siem.exporter import SIEMExporter

logger = logging.getLogger(__name__)


@shared_task
def export_pending_events():
    """
    Экспортирует ожидающие события в настроенные SIEM-системы.
    Запускается каждые 5 минут.
    """
    exporter = SIEMExporter()
    result = exporter.export_events()
    logger.info(f"SIEM export completed: {result}")
    return result


@shared_task
def retry_failed_events():
    """
    Повторяет отправку неудавшихся событий.
    Запускается каждый час.
    """
    exporter = SIEMExporter()
    retried = exporter.retry_failed()
    logger.info(f"Retried {retried} failed events")
    return retried


@shared_task
def cleanup_old_events():
    """
    Удаляет старые отправленные события.
    Запускается раз в сутки.
    """
    exporter = SIEMExporter()
    deleted = exporter.cleanup_old_events(days=30)
    logger.info(f"Cleaned up {deleted} old events")
    return deleted
