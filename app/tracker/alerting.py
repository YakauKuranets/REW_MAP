"""Tracker alerting & background checker.

Задача модуля:
  - регулярно вычислять "проблемы" по каждому устройству/наряду
  - создавать/обновлять активные алёрты в БД
  - автоматически закрывать алёрты, когда условие исчезло
  - транслировать события в UI через WebSocket (sockets.broadcast_event_sync)

Философия: безопасно для DEV, без внешних зависимостей (APScheduler и т.п.),
поэтому используется daemon thread.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

from flask import Flask

from ..extensions import db
from ..sockets import broadcast_event_sync
from .tg_notify import notify_admins_on_alert_event
from ..models import (
    TrackerDevice,
    TrackerDeviceHealth,
    TrackerAlert,
    TrackingSession,
    TrackingPoint,
    DutyShift,
)


def _utcnow() -> datetime:
    return datetime.utcnow()


@dataclass
class Thresholds:
    stale_points_sec: int = 300
    stale_health_sec: int = 180

    queue_warn: int = 50
    queue_crit: int = 150

    battery_low: int = 15
    battery_crit: int = 7

    accuracy_warn_m: int = 50
    accuracy_crit_m: int = 120

    retention_points_days: int = 90
    retention_health_log_days: int = 30

    interval_sec: int = 10


_THREAD_STARTED = False
_LOCK = threading.Lock()


def start_tracker_alert_scheduler(app: Flask) -> None:
    """Запускает фоновой чекер алёртов один раз на процесс."""
    global _THREAD_STARTED
    with _LOCK:
        if _THREAD_STARTED:
            return
        _THREAD_STARTED = True

    th = threading.Thread(target=_loop, args=(app,), daemon=True, name="tracker-alerts")
    th.start()



def tracker_alerts_tick(app: Flask) -> None:
    """Одноразовый тик алёртов (без отдельного потока).

    Полезно для отдельного worker-процесса, где мы сами управляем циклом.
    Требует активного app.app_context() у вызывающего.
    """
    thresholds = _get_thresholds(app)
    _run_once(app, thresholds)


def tracker_retention_tick(app: Flask) -> None:
    """Одноразовый тик retention (очистка старых данных).

    Требует активного app.app_context() у вызывающего.
    """
    thresholds = _get_thresholds(app)
    _run_retention(app, thresholds)

def _get_thresholds(app: Flask) -> Thresholds:
    cfg = app.config
    t = Thresholds(
        stale_points_sec=int(cfg.get('TRACKER_STALE_POINTS_SEC', 300)),
        stale_health_sec=int(cfg.get('TRACKER_STALE_HEALTH_SEC', 180)),
        queue_warn=int(cfg.get('TRACKER_QUEUE_WARN', 50)),
        queue_crit=int(cfg.get('TRACKER_QUEUE_CRIT', 150)),
        battery_low=int(cfg.get('TRACKER_BATTERY_LOW', 15)),
        battery_crit=int(cfg.get('TRACKER_BATTERY_CRIT', 7)),
        accuracy_warn_m=int(cfg.get('TRACKER_ACCURACY_WARN_M', 50)),
        accuracy_crit_m=int(cfg.get('TRACKER_ACCURACY_CRIT_M', 120)),
        retention_points_days=int(cfg.get('TRACKER_RETENTION_POINTS_DAYS', 90)),
        retention_health_log_days=int(cfg.get('TRACKER_RETENTION_HEALTH_LOG_DAYS', 30)),
        interval_sec=int(cfg.get('TRACKER_ALERTS_INTERVAL_SEC', 10)),
    )
    return t


def _loop(app: Flask) -> None:
    """Основной цикл. Работает в фоне."""
    last_retention = 0.0
    while True:
        try:
            with app.app_context():
                thresholds = _get_thresholds(app)
                _run_once(app, thresholds)

                # retention раз в сутки
                now = time.time()
                if now - last_retention >= 24 * 3600:
                    _run_retention(app, thresholds)
                    last_retention = now
        except Exception:
            try:
                app.logger.exception('tracker alert loop failed')
            except Exception:
                pass

        time.sleep(max(3, int(getattr(_get_thresholds(app), 'interval_sec', 10))))


def _run_retention(app: Flask, t: Thresholds) -> None:
    """Мягкая очистка старых данных, чтобы app.db не раздувалась бесконечно."""
    try:
        cutoff_points = _utcnow() - timedelta(days=max(7, int(t.retention_points_days)))
        # points
        db.session.query(TrackingPoint).filter(TrackingPoint.ts < cutoff_points).delete(synchronize_session=False)
        # old ended sessions snapshots are handled elsewhere; this is minimal

        cutoff_health_log = _utcnow() - timedelta(days=max(7, int(t.retention_health_log_days)))
        try:
            from ..models import TrackerDeviceHealthLog
            db.session.query(TrackerDeviceHealthLog).filter(TrackerDeviceHealthLog.ts < cutoff_health_log).delete(synchronize_session=False)
        except Exception:
            pass

        db.session.commit()
        app.logger.info('tracker retention done: points<%s, health_log<%s', cutoff_points.isoformat(), cutoff_health_log.isoformat())
    except Exception:
        db.session.rollback()
        app.logger.exception('tracker retention failed')


def _last_point_ts(user_id: str) -> Optional[datetime]:
    # предпочтение: активная сессия
    sess = TrackingSession.query.filter_by(user_id=user_id, ended_at=None).order_by(TrackingSession.started_at.desc()).first()
    if sess and sess.last_at:
        return sess.last_at

    p = TrackingPoint.query.join(TrackingSession, TrackingPoint.session_id == TrackingSession.id) \
        .filter(TrackingSession.user_id == user_id) \
        .order_by(TrackingPoint.ts.desc()).first()
    return p.ts if p else None


def _upsert_alert(
    *,
    device_id: Optional[str],
    user_id: Optional[str],
    kind: str,
    severity: str,
    message: str,
    payload: Dict[str, Any],
) -> Tuple[TrackerAlert, bool, bool]:
    """Create or update active alert. Returns (alert, created_new, changed)."""
    row = TrackerAlert.query.filter_by(device_id=device_id, user_id=user_id, kind=kind, is_active=True).order_by(TrackerAlert.created_at.desc()).first()
    created = False
    changed = False
    now = _utcnow()
    payload_json = json.dumps(payload, ensure_ascii=False)

    if not row:
        row = TrackerAlert(
            device_id=device_id,
            user_id=user_id,
            kind=kind,
            severity=severity,
            message=message,
            payload_json=payload_json,
            created_at=now,
            updated_at=now,
            is_active=True,
        )
        db.session.add(row)
        created = True
        changed = True
    else:
        # обновляем только если что-то реально поменялось (чтобы не спамить WS/БД каждый тик)
        if (row.severity != severity) or (row.message != message) or ((row.payload_json or '') != (payload_json or '')):
            row.severity = severity
            row.message = message
            row.payload_json = payload_json
            row.updated_at = now
            changed = True

    return row, created, changed

def _close_alert(device_id: Optional[str], user_id: Optional[str], kind: str) -> bool:
    """Close active alert if exists. Returns True if closed."""
    row = TrackerAlert.query.filter_by(device_id=device_id, user_id=user_id, kind=kind, is_active=True).order_by(TrackerAlert.created_at.desc()).first()
    if not row:
        return False
    row.is_active = False
    row.closed_at = _utcnow()
    row.closed_by = 'auto'
    row.updated_at = row.closed_at
    return True


def _run_once(app: Flask, t: Thresholds) -> None:
    now = _utcnow()

    devices = TrackerDevice.query.order_by(TrackerDevice.created_at.desc()).all()
    changes = []

    for d in devices:
        # HEALTH
        h = TrackerDeviceHealth.query.filter_by(device_id=d.public_id).first()
        health_ts = h.updated_at if (h and h.updated_at) else None
        point_ts = _last_point_ts(d.user_id)

        # stale points
        if point_ts and (now - point_ts).total_seconds() > t.stale_points_sec:
            sec = int((now - point_ts).total_seconds())
            msg = f"Нет точек {sec//60} мин"
            al, created, changed = _upsert_alert(
                device_id=d.public_id,
                user_id=d.user_id,
                kind='stale_points',
                severity='warn' if sec < 2 * t.stale_points_sec else 'crit',
                message=msg,
                payload={'last_point_ts': point_ts.isoformat(), 'age_sec': sec},
            )
            if created:
                changes.append(('created', al))
            elif changed:
                changes.append(('updated', al))
        else:
            if _close_alert(d.public_id, d.user_id, 'stale_points'):
                changes.append(('closed', ('stale_points', d.public_id, d.user_id)))

        # stale health
        if health_ts and (now - health_ts).total_seconds() > t.stale_health_sec:
            sec = int((now - health_ts).total_seconds())
            msg = f"Нет health {sec//60} мин"
            al, created, changed = _upsert_alert(
                device_id=d.public_id,
                user_id=d.user_id,
                kind='stale_health',
                severity='warn' if sec < 2 * t.stale_health_sec else 'crit',
                message=msg,
                payload={'last_health_ts': health_ts.isoformat(), 'age_sec': sec},
            )
            if created:
                changes.append(('created', al))
            elif changed:
                changes.append(('updated', al))
        else:
            if _close_alert(d.public_id, d.user_id, 'stale_health'):
                changes.append(('closed', ('stale_health', d.public_id, d.user_id)))

        # low battery / queue / gps
        if h:
            if h.battery_pct is not None and (h.is_charging is not True):
                if h.battery_pct <= t.battery_crit:
                    al, created, changed = _upsert_alert(
                        device_id=d.public_id,
                        user_id=d.user_id,
                        kind='battery_low',
                        severity='crit',
                        message=f"Батарея {h.battery_pct}%",
                        payload={'battery_pct': h.battery_pct, 'is_charging': h.is_charging},
                    )
                    if created:
                        changes.append(('created', al))
                    elif changed:
                        changes.append(('updated', al))
                elif h.battery_pct <= t.battery_low:
                    al, created, changed = _upsert_alert(
                        device_id=d.public_id,
                        user_id=d.user_id,
                        kind='battery_low',
                        severity='warn',
                        message=f"Батарея {h.battery_pct}%",
                        payload={'battery_pct': h.battery_pct, 'is_charging': h.is_charging},
                    )
                    if created:
                        changes.append(('created', al))
                    elif changed:
                        changes.append(('updated', al))
                else:
                    if _close_alert(d.public_id, d.user_id, 'battery_low'):
                        changes.append(('closed', ('battery_low', d.public_id, d.user_id)))
            else:
                if _close_alert(d.public_id, d.user_id, 'battery_low'):
                    changes.append(('closed', ('battery_low', d.public_id, d.user_id)))

            if h.queue_size is not None:
                if h.queue_size >= t.queue_crit:
                    al, created, changed = _upsert_alert(
                        device_id=d.public_id,
                        user_id=d.user_id,
                        kind='queue_growing',
                        severity='crit',
                        message=f"Очередь {h.queue_size}",
                        payload={'queue_size': h.queue_size},
                    )
                    if created:
                        changes.append(('created', al))
                    elif changed:
                        changes.append(('updated', al))
                elif h.queue_size >= t.queue_warn:
                    al, created, changed = _upsert_alert(
                        device_id=d.public_id,
                        user_id=d.user_id,
                        kind='queue_growing',
                        severity='warn',
                        message=f"Очередь {h.queue_size}",
                        payload={'queue_size': h.queue_size},
                    )
                    if created:
                        changes.append(('created', al))
                    elif changed:
                        changes.append(('updated', al))
                else:
                    if _close_alert(d.public_id, d.user_id, 'queue_growing'):
                        changes.append(('closed', ('queue_growing', d.public_id, d.user_id)))

            gps = (h.gps or '').strip().lower()
            if gps in ('off', 'denied'):
                al, created, changed = _upsert_alert(
                    device_id=d.public_id,
                    user_id=d.user_id,
                    kind='gps_off',
                    severity='crit' if gps == 'denied' else 'warn',
                    message=f"GPS: {gps}",
                    payload={'gps': gps},
                )
                if created:
                    changes.append(('created', al))
                elif changed:
                    changes.append(('updated', al))
            else:
                if _close_alert(d.public_id, d.user_id, 'gps_off'):
                    changes.append(('closed', ('gps_off', d.public_id, d.user_id)))

            # net offline
            net = (h.net or '').strip().lower()
            if net in ('none', 'offline'):
                sev = 'crit' if (h.tracking_on is True) else 'warn'
                al, created, changed = _upsert_alert(
                    device_id=d.public_id,
                    user_id=d.user_id,
                    kind='net_offline',
                    severity=sev,
                    message=f"Сеть: {net}",
                    payload={'net': net, 'tracking_on': h.tracking_on},
                )
                if created:
                    changes.append(('created', al))
                elif changed:
                    changes.append(('updated', al))
            else:
                if _close_alert(d.public_id, d.user_id, 'net_offline'):
                    changes.append(('closed', ('net_offline', d.public_id, d.user_id)))

            # low accuracy (only when tracking ON)
            if (h.accuracy_m is not None) and (h.tracking_on is True):
                try:
                    acc = float(h.accuracy_m)
                except Exception:
                    acc = None
                if acc is not None:
                    if acc >= float(t.accuracy_crit_m):
                        al, created, changed = _upsert_alert(
                            device_id=d.public_id,
                            user_id=d.user_id,
                            kind='low_accuracy',
                            severity='crit',
                            message=f"Точность {int(acc)} м",
                            payload={'accuracy_m': acc, 'warn_m': t.accuracy_warn_m, 'crit_m': t.accuracy_crit_m},
                        )
                        if created:
                            changes.append(('created', al))
                        elif changed:
                            changes.append(('updated', al))
                    elif acc >= float(t.accuracy_warn_m):
                        al, created, changed = _upsert_alert(
                            device_id=d.public_id,
                            user_id=d.user_id,
                            kind='low_accuracy',
                            severity='warn',
                            message=f"Точность {int(acc)} м",
                            payload={'accuracy_m': acc, 'warn_m': t.accuracy_warn_m, 'crit_m': t.accuracy_crit_m},
                        )
                        if created:
                            changes.append(('created', al))
                        elif changed:
                            changes.append(('updated', al))
                    else:
                        if _close_alert(d.public_id, d.user_id, 'low_accuracy'):
                            changes.append(('closed', ('low_accuracy', d.public_id, d.user_id)))
            else:
                if _close_alert(d.public_id, d.user_id, 'low_accuracy'):
                    changes.append(('closed', ('low_accuracy', d.public_id, d.user_id)))

            # app error (from last_error)
            err = (h.last_error or '').strip()
            if err:
                low = err.lower()
                sev = 'crit' if ('401' in low or '403' in low or 'unauthor' in low) else 'warn'
                short = err if len(err) <= 140 else (err[:140] + '…')
                al, created, changed = _upsert_alert(
                    device_id=d.public_id,
                    user_id=d.user_id,
                    kind='app_error',
                    severity=sev,
                    message=f"Ошибка: {short}",
                    payload={'last_error': err},
                )
                if created:
                    changes.append(('created', al))
                elif changed:
                    changes.append(('updated', al))
            else:
                if _close_alert(d.public_id, d.user_id, 'app_error'):
                    changes.append(('closed', ('app_error', d.public_id, d.user_id)))

            # tracking OFF while shift is active
            try:
                active_shift = DutyShift.query.filter_by(user_id=d.user_id, ended_at=None).first()
            except Exception:
                active_shift = None
            if active_shift and (h.tracking_on is False):
                al, created, changed = _upsert_alert(
                    device_id=d.public_id,
                    user_id=d.user_id,
                    kind='tracking_off',
                    severity='warn',
                    message="Трекинг выключен (в смене)",
                    payload={'tracking_on': h.tracking_on, 'shift_id': getattr(active_shift, 'id', None)},
                )
                if created:
                    changes.append(('created', al))
                elif changed:
                    changes.append(('updated', al))
            else:
                if _close_alert(d.public_id, d.user_id, 'tracking_off'):
                    changes.append(('closed', ('tracking_off', d.public_id, d.user_id)))



    if not changes:
        return

    db.session.commit()

    # события в UI
    for kind, data in changes:
        try:
            if kind in ('created', 'updated') and isinstance(data, TrackerAlert):
                broadcast_event_sync('tracker_alert', data.to_dict())
                try:
                    notify_admins_on_alert_event(kind, data)
                except Exception:
                    pass
            elif kind == 'closed' and isinstance(data, tuple):
                akind, device_id, user_id = data
                broadcast_event_sync('tracker_alert_closed', {'kind': akind, 'device_id': device_id, 'user_id': user_id})
        except Exception:
            pass
