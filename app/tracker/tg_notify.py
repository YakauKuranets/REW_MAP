from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

from flask import current_app

from ..extensions import db
from ..integrations.telegram_sender import send_telegram_message
from ..models import TrackerAlert, TrackerAlertNotifyLog, TrackerDevice


def _parse_csv_set(raw: str) -> set[str]:
    out: set[str] = set()
    for x in (raw or '').split(','):
        s = (x or '').strip()
        if s:
            out.add(s.lower())
    return out


def _now_utc() -> datetime:
    return datetime.utcnow()


def _digest_text(text: str) -> str:
    return hashlib.sha256((text or '').encode('utf-8', errors='ignore')).hexdigest()[:16]


def _get_public_base_url() -> str:
    # для ссылок в TG. Prefer BOOTSTRAP_PREFERRED_BASE_URL (Cloudflare domain).
    base = (current_app.config.get('BOOTSTRAP_PREFERRED_BASE_URL') or '').strip().rstrip('/')
    return base


def _format_admin_link(device_id: Optional[str]) -> str:
    base = _get_public_base_url()
    if not device_id:
        return (base + "/admin/problems") if base else "/admin/problems"
    if base:
        return f"{base}/admin/devices/{device_id}"
    return f"/admin/devices/{device_id}"


def _recommendations_for_alert(alert: TrackerAlert) -> List[str]:
    # Мини-копия логики из static/js/recs.js — только самые полезные пункты для Telegram.
    kind = (alert.kind or '').lower().strip()
    payload = alert.payload() if alert else {}
    rec: List[str] = []

    if kind == 'net_offline':
        rec += [
            'Проверьте интернет (Wi‑Fi/моб. данные), отключите режим полёта',
            'Разрешите фоновую передачу данных для DutyTracker',
        ]
    elif kind == 'gps_off':
        rec += [
            'Включите геолокацию (GPS) и режим «Высокая точность»',
            'Проверьте разрешение геолокации «Всегда» для DutyTracker',
        ]
    elif kind == 'low_accuracy':
        rec += [
            'Перейдите на открытое место; включите «Высокая точность» (GPS + Wi‑Fi/BT)',
            'Отключите энергосбережение / battery optimization для DutyTracker',
        ]
    elif kind == 'tracking_off':
        rec += [
            'Откройте DutyTracker и включите трекинг',
            'Проверьте, что смена запущена (если требуется)',
        ]
    elif kind == 'stale_points':
        rec += [
            'Нет свежих точек: проверьте сеть и ограничения фоновой работы',
            'Убедитесь, что Foreground Service активен и трекинг включён',
        ]
    elif kind == 'stale_health':
        rec += [
            'Heartbeat не приходит: откройте приложение и проверьте сеть',
            'Отключите battery optimization для DutyTracker',
        ]
    elif kind == 'queue_growing':
        rec += [
            'Очередь растёт: плохая сеть или ограничения фоновой работы',
            'Смените сеть (Wi‑Fi/моб. данные) или дождитесь восстановления',
        ]
    elif kind == 'battery_low':
        rec += [
            'Низкий заряд: подключите зарядку',
            'Отключите энергосбережение для DutyTracker (может ломать фон)',
        ]
    elif kind == 'app_error':
        rec += [
            'Откройте DutyTracker и посмотрите текст ошибки',
            'Проверьте BASE_URL/доступность сервера и токен',
            'Перезапустите приложение (или переустановите при повторении)',
        ]

    # лёгкая подсказка по payload
    try:
        acc = float(payload.get('accuracy_m') or 0)
        if acc > 0:
            rec.append(f'Текущая точность: ~{int(round(acc))} м')
    except Exception:
        pass
    try:
        age = float(payload.get('age_sec') or 0)
        if age > 0:
            rec.append(f'Возраст данных: ~{int(round(age/60.0))} мин')
    except Exception:
        pass

    # uniq, максимум 3
    seen: set[str] = set()
    out: List[str] = []
    for s in rec:
        k = s.strip().lower()
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(s.strip())
        if len(out) >= 3:
            break
    return out


def _should_notify(alert: TrackerAlert) -> bool:
    token = (current_app.config.get('TELEGRAM_BOT_TOKEN') or '').strip()
    admin_ids = current_app.config.get('ADMIN_TELEGRAM_IDS') or set()
    if not token or not admin_ids:
        return False

    # Включатель: если явно выключили — не шлём
    enabled = str(current_app.config.get('TRACKER_TG_ALERT_NOTIFY', '1')).strip()
    if enabled in ('0', 'false', 'False', 'off', 'OFF'):
        return False

    severities = _parse_csv_set(str(current_app.config.get('TRACKER_TG_NOTIFY_SEVERITIES', 'crit')))
    kinds = _parse_csv_set(str(current_app.config.get('TRACKER_TG_NOTIFY_KINDS', '')))
    if severities and (str(alert.severity or '').lower() not in severities):
        return False
    if kinds and (str(alert.kind or '').lower() not in kinds):
        return False
    return True


def _throttle_ok(device_id: Optional[str], kind: str, chat_id: str) -> bool:
    min_sec = int(current_app.config.get('TRACKER_TG_NOTIFY_MIN_INTERVAL_SEC', 900) or 900)
    if min_sec <= 0:
        return True
    cutoff = _now_utc() - timedelta(seconds=min_sec)
    last = (
        TrackerAlertNotifyLog.query
        .filter_by(device_id=device_id, kind=kind, sent_to=str(chat_id))
        .order_by(TrackerAlertNotifyLog.sent_at.desc())
        .first()
    )
    if not last or not last.sent_at:
        return True
    return last.sent_at < cutoff


def notify_admins_on_alert_event(event: str, alert: TrackerAlert) -> None:
    """Best-effort уведомление в Telegram админам при событии по алёрту.

    event: created / updated / closed
    """
    try:
        if not alert or not _should_notify(alert):
            return

        token = (current_app.config.get('TELEGRAM_BOT_TOKEN') or '').strip()
        admin_ids = list(current_app.config.get('ADMIN_TELEGRAM_IDS') or [])
        if not token or not admin_ids:
            return

        device_label = None
        if alert.device_id:
            d = TrackerDevice.query.filter_by(public_id=alert.device_id).first()
            device_label = (d.label if d else None) or alert.device_id

        sev = (alert.severity or 'warn').upper()
        kind = (alert.kind or '').strip()
        msg = (alert.message or '').strip()

        link = _format_admin_link(alert.device_id)
        recs = _recommendations_for_alert(alert)

        header = f"[{sev}] {kind}"
        if device_label:
            header += f" — {device_label}"

        lines = [header]
        if msg:
            lines.append(msg)
        if recs:
            lines.append("Рекомендуется:")
            for r in recs:
                lines.append(f"- {r}")
        lines.append(f"Открыть: {link}")

        text = "\n".join(lines).strip()
        digest = _digest_text(text)

        for chat_id in admin_ids:
            try:
                if not _throttle_ok(alert.device_id, kind.lower(), str(chat_id)):
                    continue

                payload = send_telegram_message(token, str(chat_id), text, disable_web_preview=True, timeout_sec=8)
                ok = bool(payload.get('ok'))
                if ok:
                    row = TrackerAlertNotifyLog(
                        device_id=alert.device_id,
                        user_id=alert.user_id,
                        kind=kind.lower(),
                        severity=str(alert.severity or '').lower(),
                        sent_to=str(chat_id),
                        digest=digest,
                    )
                    db.session.add(row)
                    db.session.commit()
            except Exception:
                try:
                    db.session.rollback()
                except Exception:
                    pass
                continue

    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass
        return
