"""Duty API: смены (начало/конец), check-in, live-геотрекинг, обеды, журнал.

Цели:
- Принимать координаты от Telegram-бота (одноразовые и live).
- Давать администратору панель контроля (dashboard + approve/end break).
- Хранить историю (точки, стоянки, события смены).
- Отправлять уведомления наряду через polling бота.
"""

from __future__ import annotations

import json
import os
import math
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from flask import current_app, jsonify, request, render_template

from sqlalchemy import desc

from . import bp
from ..extensions import db
from ..helpers import require_admin, haversine_m
from ..sockets import broadcast_event_sync
from ..models import DutyShift, DutyEvent, TrackingSession, TrackingPoint, TrackingStop, BreakRequest, DutyNotification, SosAlert, TrackerDeviceHealth, TrackerDevice
from ..security.api_keys import require_bot_api_key
from ..security.rate_limit import check_rate_limit


# -------------------------
# Auth helpers
# -------------------------

def _require_bot_key() -> Optional[Tuple[Dict[str, Any], int]]:
    """Проверка ключа для bot-эндпоинтов.

    Сохраняем прежний интерфейс: возвращаем (json, code) либо None.
    """
    try:
        require_bot_api_key(allow_query_param=False)
        return None
    except Exception:
        # abort(403) перехватывать не нужно; но на всякий случай возвращаем JSON
        return ({'error': 'Unauthorized'}, 403)


def _bot_rate_limit(bucket: str, limit_key: str, default_limit: int) -> Optional[Tuple[Dict[str, Any], int]]:
    """Best-effort rate limit для bot endpoint'ов."""
    try:
        ip = (request.headers.get("X-Forwarded-For") or request.remote_addr or "unknown").split(",")[0].strip()
        limit = int(current_app.config.get(limit_key, default_limit))
        ok, _info = check_rate_limit(bucket=bucket, ident=ip, limit=limit, window_seconds=60)
        if not ok:
            return ({'error': 'rate_limited'}, 429)
    except Exception:
        pass
    return None


# -------------------------
# Tracking meta helpers
# -------------------------

def _tp_meta(tp: Optional[TrackingPoint]) -> Dict[str, Any]:
    """Достаём доп. поля точки из raw_json (без миграций БД)."""
    if not tp:
        return {}
    try:
        meta = json.loads(tp.raw_json or "{}") if tp.raw_json else {}
        return meta if isinstance(meta, dict) else {}
    except Exception:
        return {}

def _last_meta_fields(tp: Optional[TrackingPoint]) -> Dict[str, Any]:
    meta = _tp_meta(tp)
    out: Dict[str, Any] = {}

    # base fields (used widely in UI)
    spd = meta.get("speed_mps")
    brg = meta.get("bearing_deg")
    flags = meta.get("flags") or []
    try:
        out["speed_mps"] = float(spd) if spd is not None else None
    except Exception:
        out["speed_mps"] = None
    try:
        out["bearing_deg"] = float(brg) if brg is not None else None
    except Exception:
        out["bearing_deg"] = None
    out["flags"] = flags if isinstance(flags, list) else []

    # source/mode (MAX indoor diagnostics)
    src = meta.get("src") or meta.get("source")
    try:
        if not src and tp is not None:
            if tp.kind == "est":
                src = "wifi_est"
            elif tp.kind:
                src = str(tp.kind)
            else:
                src = "app"
    except Exception:
        pass
    if src:
        out["source"] = str(src)

    # numeric diagnostics for estimated points (optional)
    for k, cast in (
        ("confidence", float),
        ("matches", int),
        ("matches_wifi", int),
        ("matches_cell", int),
        ("rssi_diff_avg_db", float),
        ("cell_diff_avg_db", float),
        ("tiles_considered", int),
        ("spread_m", float),
        ("anchors_considered", int),
        ("clusters_total", int),
        ("clusters_used", int),
    ):
        if k in meta:
            try:
                out[k] = cast(meta.get(k))
            except Exception:
                out[k] = meta.get(k)

    # string diagnostics (optional)
    for k in ("method", "tile_id"):
        if k in meta:
            try:
                out[k] = str(meta.get(k))
            except Exception:
                out[k] = meta.get(k)


    # timestamps / misc
    if "anchor_ts" in meta:
        try:
            out["anchor_ts"] = str(meta.get("anchor_ts"))
        except Exception:
            out["anchor_ts"] = meta.get("anchor_ts")

    return out

def _kpi_5m_for_session(session_id: Optional[int], now: datetime) -> Optional[Dict[str, Any]]:
    if not session_id:
        return None
    since = now - timedelta(minutes=5)
    try:
        # ограничим объём выборки на случай частых точек
        pts = (TrackingPoint.query
               .filter_by(session_id=session_id)
               .filter(TrackingPoint.ts >= since)
               .order_by(desc(TrackingPoint.ts))
               .limit(500)
               .all())
    except Exception:
        return None

    if not pts:
        return {"points_5m": 0, "acc_avg_5m": None, "jumps_5m": 0}

    accs = [p.accuracy_m for p in pts if p.accuracy_m is not None]
    acc_avg = None
    if accs:
        try:
            acc_avg = round(sum(accs) / len(accs), 1)
        except Exception:
            acc_avg = None

    jumps = 0
    for p in pts:
        try:
            flags = _tp_meta(p).get("flags") or []
            if isinstance(flags, list) and ("jump" in flags):
                jumps += 1
        except Exception:
            pass

    return {"points_5m": len(pts), "acc_avg_5m": acc_avg, "jumps_5m": jumps}


# -------------------------
# MAX-3: display-point hysteresis (GNSS ↔ indoor estimate)
# -------------------------

def _is_est_point(tp: Optional[TrackingPoint], meta: Optional[Dict[str, Any]] = None) -> bool:
    if not tp:
        return False
    m = meta if isinstance(meta, dict) else _tp_meta(tp)
    src = (m.get("src") or m.get("source") or "")
    flags = m.get("flags") or []
    try:
        if tp.kind == "est":
            return True
    except Exception:
        pass
    try:
        if isinstance(flags, list) and ("est" in flags):
            return True
    except Exception:
        pass
    return str(src).lower() == "wifi_est"

def _is_good_gnss(tp: Optional[TrackingPoint], meta: Optional[Dict[str, Any]] = None) -> bool:
    if not tp:
        return False
    m = meta if isinstance(meta, dict) else _tp_meta(tp)
    flags = m.get("flags") or []
    try:
        if isinstance(flags, list) and ("jump" in flags):
            return False
    except Exception:
        pass
    try:
        if tp.kind == "est":
            return False
    except Exception:
        pass
    try:
        acc = float(tp.accuracy_m) if tp.accuracy_m is not None else None
    except Exception:
        acc = None
    # strict good GNSS
    try:
        max_acc = float(current_app.config.get('DISPLAY_GOOD_GNSS_MAX_ACC_M', 60))
    except Exception:
        max_acc = 60.0
    return (acc is not None) and (acc > 0) and (acc <= max_acc)

def _select_display_point(session_id: int, now: datetime) -> Optional[TrackingPoint]:
    """Pick the point used for UI (map + sidebar) with hysteresis.

    Problem: indoors GNSS may intermittently produce a 'newer' but wrong point that causes jumps.
    Solution: when we have a fresh estimate (wifi_est), keep it until GNSS becomes stably good.
    """
    try:
        pts: List[TrackingPoint] = (TrackingPoint.query
                                   .filter_by(session_id=session_id)
                                   .order_by(desc(TrackingPoint.ts))
                                   .limit(30)
                                   .all())
    except Exception:
        pts = []

    if not pts:
        return None

    # tuning knobs (env/config)
    try:
        est_fresh_sec = float(current_app.config.get('DISPLAY_EST_FRESH_SEC', 120))
    except Exception:
        est_fresh_sec = 120.0
    try:
        stable_window_sec = float(current_app.config.get('DISPLAY_GNSS_STABLE_WINDOW_SEC', 25))
    except Exception:
        stable_window_sec = 25.0
    try:
        stable_dist_m = float(current_app.config.get('DISPLAY_GNSS_STABLE_DIST_M', 50))
    except Exception:
        stable_dist_m = 50.0

    # first pass: find candidates
    est_tp = None
    gnss_good = []
    gnss_any = None
    for p in pts:
        meta = _tp_meta(p)
        if est_tp is None and _is_est_point(p, meta):
            est_tp = p
        if gnss_any is None and (not _is_est_point(p, meta)):
            gnss_any = p
        if (not _is_est_point(p, meta)) and _is_good_gnss(p, meta):
            gnss_good.append(p)

    # freshness windows
    def _age_sec(p: TrackingPoint) -> float:
        try:
            return (now - (p.ts or now)).total_seconds()
        except Exception:
            return 9999.0

    est_fresh = est_tp is not None and _age_sec(est_tp) <= est_fresh_sec
    if est_fresh and gnss_good:
        # require stable GNSS: at least 2 good points within ~25 sec and not far apart
        recent_good = [p for p in gnss_good if _age_sec(p) <= stable_window_sec]
        if len(recent_good) >= 2:
            try:
                d = _haversine_m(float(recent_good[0].lat), float(recent_good[0].lon), float(recent_good[1].lat), float(recent_good[1].lon))
            except Exception:
                d = 9999.0
            if d <= stable_dist_m:
                return recent_good[0]  # newest stable GNSS
        # otherwise keep estimate to prevent jumping
        return est_tp

    if est_fresh and not gnss_good:
        return est_tp

    # no estimate (or stale): prefer good GNSS, else any last
    if gnss_good:
        return gnss_good[0]
    return pts[0]

# -------------------------
# Utility
# -------------------------

def _utcnow() -> datetime:
    return datetime.utcnow()


def _compute_device_status(now: datetime, last_point_ts: Optional[datetime], heartbeat_ts: Optional[datetime]) -> Dict[str, Any]:
    """Единая логика статуса устройства для UI.

    Статусы:
      - on_air    : обновления совсем недавно
      - no_signal : обновления были, но давно
      - offline   : очень давно / нет данных

    Важно: считаем по "последней точке" и "heartbeat" (last_seen/health).
    """

    def _age(ts: Optional[datetime]) -> Optional[int]:
        if not ts:
            return None
        try:
            return int((now - ts).total_seconds())
        except Exception:
            return None

    on_air_sec = int(current_app.config.get('DEVICE_STATUS_ON_AIR_SEC', 90))
    no_signal_sec = int(current_app.config.get('DEVICE_STATUS_NO_SIGNAL_SEC', 600))

    lp_age = _age(last_point_ts)
    hb_age = _age(heartbeat_ts)

    # last update = max(last_point_ts, heartbeat_ts)
    last_update_ts: Optional[datetime] = None
    try:
        if last_point_ts and heartbeat_ts:
            last_update_ts = last_point_ts if last_point_ts >= heartbeat_ts else heartbeat_ts
        else:
            last_update_ts = last_point_ts or heartbeat_ts
    except Exception:
        last_update_ts = last_point_ts or heartbeat_ts

    upd_age = _age(last_update_ts)

    code = 'offline'
    label = 'Не в сети'
    basis = 'none'
    if upd_age is None:
        code = 'offline'
        label = 'Не в сети'
        basis = 'none'
    elif upd_age <= on_air_sec:
        code = 'on_air'
        label = 'В эфире'
        # уточняем основу
        if lp_age is not None and lp_age <= on_air_sec:
            basis = 'point'
        elif hb_age is not None and hb_age <= on_air_sec:
            basis = 'heartbeat'
        else:
            basis = 'recent'
    elif upd_age <= no_signal_sec:
        code = 'no_signal'
        label = 'Нет связи'
        basis = 'stale'
    else:
        code = 'offline'
        label = 'Не в сети'
        basis = 'offline'

    return {
        'code': code,
        'label': label,
        'basis': basis,
        'last_update_at': last_update_ts.isoformat() if last_update_ts else None,
        'last_update_age_sec': upd_age,
        'last_point_age_sec': lp_age,
        'heartbeat_age_sec': hb_age,
    }


def _log_event(user_id: str, shift_id: Optional[int], event_type: str, actor: str = 'system', payload: Optional[Dict[str, Any]] = None) -> None:
    ev = DutyEvent(
        user_id=str(user_id),
        shift_id=shift_id,
        ts=_utcnow(),
        event_type=event_type,
        actor=actor,
        payload_json=json.dumps(payload or {}, ensure_ascii=False),
    )
    db.session.add(ev)


def _get_active_shift(user_id: str) -> Optional[DutyShift]:
    return DutyShift.query.filter_by(user_id=str(user_id), ended_at=None).order_by(desc(DutyShift.started_at)).first()


def _get_or_create_active_shift(user_id: str, unit_label: Optional[str] = None) -> DutyShift:
    """Вернуть активную смену для user_id, либо создать новую (авто-старт).

    Это нужно, чтобы любые события (check-in, обед, SOS, live-гео) могли
    корректно привязаться к смене, даже если наряд не нажал "Начало службы".
    """
    sh = _get_active_shift(user_id)
    if sh:
        if unit_label and (not sh.unit_label):
            sh.unit_label = unit_label
        return sh

    sh = DutyShift(
        user_id=str(user_id),
        unit_label=(unit_label or '').strip()[:64] or None,
        started_at=_utcnow(),
    )
    db.session.add(sh)
    db.session.flush()  # получить id
    _log_event(user_id, sh.id, 'SHIFT_AUTO_START', actor='system', payload={'reason': 'no_active_shift'})
    return sh


def _get_last_location(user_id: str) -> Optional[Dict[str, Any]]:
    """Последняя известная точка для пользователя.

    Сначала смотрим активную live-сессию (если есть), иначе берём последнюю
    точку из истории (TrackingPoint).
    """
    uid = str(user_id)
    sess = TrackingSession.query.filter_by(user_id=uid, ended_at=None).order_by(desc(TrackingSession.started_at)).first()
    if sess and sess.last_lat is not None and sess.last_lon is not None:
        return {
            'lat': sess.last_lat,
            'lon': sess.last_lon,
            'accuracy_m': None,
            'ts': sess.last_at.isoformat() if sess.last_at else None,
            'session_id': sess.id,
        }

    lp = TrackingPoint.query.filter_by(user_id=uid).order_by(desc(TrackingPoint.ts)).first()
    if lp:
        return {
            'lat': lp.lat,
            'lon': lp.lon,
            'accuracy_m': lp.accuracy_m,
            'ts': lp.ts.isoformat() if lp.ts else None,
            'session_id': lp.session_id,
        }
    return None


def _ensure_tracks_dir() -> str:
    up = current_app.config.get('UPLOAD_FOLDER') or os.path.join(current_app.root_path, '..', 'uploads')
    tracks_dir = os.path.join(up, 'tracks')
    os.makedirs(tracks_dir, exist_ok=True)
    return tracks_dir


def _svg_escape(s: str) -> str:
    return (s or '').replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('"','&quot;')


def _build_route_svg(points: List[TrackingPoint], stops: List[TrackingStop], width: int = 900, height: int = 520) -> str:
    # Схематический рисунок без подложки карты: нормализуем координаты в прямоугольник.
    if not points:
        return f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}'><text x='20' y='40'>Нет данных</text></svg>"

    lats = [p.lat for p in points if p.lat is not None]
    lons = [p.lon for p in points if p.lon is not None]
    if not lats or not lons:
        return f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}'><text x='20' y='40'>Нет координат</text></svg>"
    min_lat, max_lat = min(lats), max(lats)
    min_lon, max_lon = min(lons), max(lons)

    # запас
    pad = 0.0005
    min_lat -= pad; max_lat += pad
    min_lon -= pad; max_lon += pad

    def proj(lat: float, lon: float) -> Tuple[float,float]:
        x = (lon - min_lon) / (max_lon - min_lon + 1e-12)
        y = (lat - min_lat) / (max_lat - min_lat + 1e-12)
        # y вверх, в svg вниз
        return (20 + x*(width-40), 20 + (1-y)*(height-40))

    path = []
    for p in points:
        x,y = proj(p.lat, p.lon)
        path.append(f"{x:.2f},{y:.2f}")
    polyline = " ".join(path)

    # start/end points
    sx,sy = proj(points[0].lat, points[0].lon)
    ex,ey = proj(points[-1].lat, points[-1].lon)

    # stops markers
    stop_circles = []
    for st in stops:
        x,y = proj(st.center_lat, st.center_lon)
        dur = int(st.duration_sec or 0)
        stop_circles.append(
            f"<circle cx='{x:.2f}' cy='{y:.2f}' r='7' fill='orange' stroke='black' stroke-width='1'/>"
            f"<text x='{x+10:.2f}' y='{y+4:.2f}' font-size='12' fill='black'>{dur//60}м</text>"
        )

    return f"""<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}'>
    <rect x='0' y='0' width='{width}' height='{height}' fill='white'/>
    <polyline points='{polyline}' fill='none' stroke='blue' stroke-width='3' stroke-linejoin='round' stroke-linecap='round'/>
    <circle cx='{sx:.2f}' cy='{sy:.2f}' r='8' fill='green' stroke='black' stroke-width='1'/>
    <circle cx='{ex:.2f}' cy='{ey:.2f}' r='8' fill='red' stroke='black' stroke-width='1'/>
    {''.join(stop_circles)}
    <text x='20' y='{height-15}' font-size='12' fill='#444'>start=green, end=red, стоянки=orange</text>
    </svg>"""


def _compute_stops(points: List[TrackingPoint], radius_m: float = 10.0, min_sec: int = 60) -> List[TrackingStop]:
    # простой алгоритм: скользящее окно "пока рядом" — считаем сегмент стоянки.
    stops: List[TrackingStop] = []
    if len(points) < 2:
        return stops

    i = 0
    while i < len(points)-1:
        p0 = points[i]
        j = i+1
        cluster = [p0]
        while j < len(points):
            pj = points[j]
            if haversine_m(p0.lat, p0.lon, pj.lat, pj.lon) <= radius_m:
                cluster.append(pj)
                j += 1
            else:
                break
        if len(cluster) >= 2:
            dt = (cluster[-1].ts - cluster[0].ts).total_seconds()
            if dt >= min_sec:
                lat_c = sum(p.lat for p in cluster)/len(cluster)
                lon_c = sum(p.lon for p in cluster)/len(cluster)
                st = TrackingStop(
                    session_id=points[i].session_id,
                    start_ts=cluster[0].ts,
                    end_ts=cluster[-1].ts,
                    center_lat=lat_c,
                    center_lon=lon_c,
                    duration_sec=int(dt),
                    radius_m=int(radius_m),
                    points_count=len(cluster),
                )
                stops.append(st)
                i = j
                continue
        i += 1
    return stops


def _create_notification(user_id: str, kind: str, text: str, payload: Optional[Dict[str, Any]] = None) -> None:
    n = DutyNotification(
        user_id=str(user_id),
        created_at=_utcnow(),
        kind=kind,
        text=text[:3500],
        payload_json=json.dumps(payload or {}, ensure_ascii=False),
        acked=False,
    )
    db.session.add(n)


# -------------------------
# Pages
# -------------------------

@bp.get('/admin/duty')
def admin_duty_page():
    require_admin("viewer")
    return render_template('admin_duty.html')


@bp.get('/admin/panel')
def admin_panel_page():
    """Командный центр оператора: единая админ-панель (карта + списки)."""
    require_admin("viewer")
    return render_template('admin_panel.html')


@bp.get('/admin/devices')
def admin_devices_page():
    """Страница устройств трекера (Android).

    Здесь диспетчер видит:
      - last_seen / health
      - связь с активной сменой
      - revoke/restore
    """
    require_admin("viewer")
    return render_template('admin_devices.html')


@bp.get('/admin/service')
def admin_service_page():
    """Заявки на доступ к «Службе» + привязка DutyTracker (bootstrap)."""
    require_admin("viewer")
    return render_template('admin_service.html')


@bp.get('/admin/devices/<string:device_id>')
def admin_device_detail_page(device_id: str):
    """Drill-down страница одного устройства."""
    require_admin("viewer")
    return render_template('admin_device_detail.html', device_id=device_id)


@bp.get('/admin/problems')
def admin_problems_page():
    """Панель проблем/алёртов трекера.

    Техническая страница: диспетчер видит активные алёрты (stale/queue/battery/gps…) и может ACK/CLOSE.
    """
    require_admin("viewer")
    return render_template('admin_problems.html')

@bp.get('/admin/metrics')
def admin_metrics_page():
    """Оперативные метрики (KPI/алёрты) для мониторинга."""
    require_admin("viewer")
    return render_template('admin_metrics.html')


@bp.get('/admin/incidents')
def admin_incidents_page():
    """Страница управления инцидентами.

    Здесь диспетчер может искать и фильтровать оперативные
    инциденты, смотреть ключевые показатели (KPI) и переходить
    к подробной информации. Для доступа требуется роль
    ``viewer``.
    """
    require_admin("viewer")
    return render_template('admin_incidents.html')


@bp.get('/admin/objects')
def admin_objects_page():
    """Страница объектов/адресов (импорт/экспорт, быстрые действия)."""
    require_admin("viewer")
    return render_template('admin_objects.html')


# ---------------------------------------------------------------------------
# Incident detail page
# ---------------------------------------------------------------------------

@bp.get('/admin/incidents/<int:incident_id>')
def admin_incident_detail_page(incident_id: int):
    """Страница деталей инцидента.

    Позволяет просмотреть информацию об инциденте, увидеть связанные
    события (таймлайн), назначить наряд и обновить статус реакции.
    Для доступа требуется роль ``viewer``.
    Действия (назначение, изменение статуса) требуют ``editor``
    и выполняются через AJAX.
    """
    require_admin("viewer")
    return render_template('admin_incident_detail.html', incident_id=incident_id)



# -------------------------
# Bot API endpoints
# -------------------------

@bp.post('/api/duty/bot/shift/start')
def api_bot_shift_start():
    bad = _require_bot_key()
    if bad:
        return jsonify(bad[0]), bad[1]
    bad = _bot_rate_limit('duty_shift_start', 'RATE_LIMIT_DUTY_SHIFT_PER_MINUTE', 120)
    if bad:
        return jsonify(bad[0]), bad[1]
    data = request.get_json(silent=True) or {}
    user_id = str(data.get('user_id') or '')
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    unit = (data.get('unit_label') or '').strip()[:64] or None
    lat = data.get('lat'); lon = data.get('lon')
    sh = _get_active_shift(user_id)
    if sh:
        # обновим label при необходимости
        if unit and not sh.unit_label:
            sh.unit_label = unit
        db.session.commit()
        return jsonify({'ok': True, 'shift_id': sh.id, 'already_active': True})

    sh = DutyShift(user_id=user_id, unit_label=unit, started_at=_utcnow(), start_lat=lat, start_lon=lon)
    db.session.add(sh)
    db.session.flush()
    _log_event(user_id, sh.id, 'SHIFT_START', actor='user', payload={'lat': lat, 'lon': lon, 'unit_label': unit})
    db.session.commit()

    broadcast_event_sync('shift_started', {'user_id': user_id, 'shift_id': sh.id, 'unit_label': sh.unit_label, 'lat': lat, 'lon': lon})
    return jsonify({'ok': True, 'shift_id': sh.id})


@bp.post('/api/duty/bot/shift/end')
def api_bot_shift_end():
    bad = _require_bot_key()
    if bad:
        return jsonify(bad[0]), bad[1]
    bad = _bot_rate_limit('duty_shift_end', 'RATE_LIMIT_DUTY_SHIFT_PER_MINUTE', 120)
    if bad:
        return jsonify(bad[0]), bad[1]
    data = request.get_json(silent=True) or {}
    user_id = str(data.get('user_id') or '')
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    lat = data.get('lat'); lon = data.get('lon')
    sh = _get_active_shift(user_id)
    if not sh:
        return jsonify({'ok': True, 'shift_id': None, 'message': 'no active shift'}), 200

    sh.ended_at = _utcnow()
    sh.end_lat = lat
    sh.end_lon = lon
    _log_event(user_id, sh.id, 'SHIFT_END', actor='user', payload={'lat': lat, 'lon': lon})
    # Закрываем активный трекинг (если есть)
    sess = TrackingSession.query.filter_by(user_id=user_id, ended_at=None).order_by(desc(TrackingSession.started_at)).first()
    if sess:
        sess.ended_at = _utcnow()
        sess.is_active = False
        _log_event(user_id, sh.id, 'TRACKING_AUTO_STOP', actor='system', payload={'session_id': sess.id, 'reason': 'shift_end'})
    db.session.commit()

    broadcast_event_sync('shift_ended', {'user_id': user_id, 'shift_id': sh.id})
    return jsonify({'ok': True, 'shift_id': sh.id})


@bp.post('/api/duty/bot/checkin')
def api_bot_checkin():
    bad = _require_bot_key()
    if bad:
        return jsonify(bad[0]), bad[1]
    bad = _bot_rate_limit('duty_checkin', 'RATE_LIMIT_DUTY_CHECKIN_PER_MINUTE', 240)
    if bad:
        return jsonify(bad[0]), bad[1]
    data = request.get_json(silent=True) or {}
    user_id = str(data.get('user_id') or '')
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    lat = data.get('lat'); lon = data.get('lon')
    note = (data.get('note') or '').strip()[:200]
    unit = (data.get('unit_label') or '').strip()[:64] or None

    sh = _get_or_create_active_shift(user_id, unit_label=unit)
    pt = TrackingPoint(session_id=None, user_id=user_id, ts=_utcnow(), lat=lat, lon=lon, accuracy_m=data.get('accuracy_m'), kind='checkin', raw_json=json.dumps(data, ensure_ascii=False))
    db.session.add(pt)
    _log_event(user_id, sh.id, 'CHECKIN', actor='user', payload={'lat': lat, 'lon': lon, 'note': note})
    db.session.commit()

    broadcast_event_sync('checkin', {'user_id': user_id, 'shift_id': sh.id, 'lat': lat, 'lon': lon, 'note': note})
    return jsonify({'ok': True, 'shift_id': sh.id})


@bp.post('/api/duty/bot/live_location')
def api_bot_live_location():
    bad = _require_bot_key()
    if bad:
        return jsonify(bad[0]), bad[1]
    bad = _bot_rate_limit('duty_live_location', 'RATE_LIMIT_DUTY_LIVE_PER_MINUTE', 600)
    if bad:
        return jsonify(bad[0]), bad[1]
    data = request.get_json(silent=True) or {}
    user_id = str(data.get('user_id') or '')
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    lat = float(data.get('lat')) if data.get('lat') is not None else None
    lon = float(data.get('lon')) if data.get('lon') is not None else None
    if lat is None or lon is None:
        return jsonify({'error': 'lat/lon required'}), 400
    message_id = data.get('message_id')
    is_live = bool(data.get('is_live', False))
    unit = (data.get('unit_label') or '').strip()[:64] or None

    sh = _get_or_create_active_shift(user_id, unit_label=unit)

    sess: Optional[TrackingSession] = None
    if is_live and message_id is not None:
        sess = TrackingSession.query.filter_by(user_id=user_id, message_id=int(message_id), ended_at=None).first()
    if is_live and sess is None:
        sess = TrackingSession(user_id=user_id, shift_id=sh.id, started_at=_utcnow(), is_active=True, message_id=int(message_id) if message_id is not None else None)
        db.session.add(sess)
        db.session.flush()
        _log_event(user_id, sh.id, 'TRACKING_START', actor='user', payload={'session_id': sess.id, 'message_id': message_id})
        broadcast_event_sync('tracking_started', {'user_id': user_id, 'shift_id': sh.id, 'session_id': sess.id, 'message_id': message_id})

    # точка
    ts = _utcnow()
    pt = TrackingPoint(session_id=sess.id if sess else None, user_id=user_id, ts=ts, lat=lat, lon=lon, accuracy_m=data.get('accuracy_m'), kind='live' if is_live else 'location', raw_json=json.dumps(data, ensure_ascii=False))
    db.session.add(pt)

    # обновим состояние сессии
    if sess:
        sess.last_lat = lat
        sess.last_lon = lon
        sess.last_at = ts
        sess.is_active = True

    _log_event(user_id, sh.id, 'TRACKING_POINT' if is_live else 'LOCATION_POINT', actor='user', payload={'session_id': sess.id if sess else None, 'lat': lat, 'lon': lon})

    db.session.commit()

    if sess:
        broadcast_event_sync('tracking_point', {'user_id': user_id, 'shift_id': sh.id, 'session_id': sess.id, 'lat': lat, 'lon': lon, 'ts': ts.isoformat()})

    return jsonify({'ok': True, 'shift_id': sh.id, 'session_id': sess.id if sess else None})


@bp.post('/api/duty/bot/tracking/stop')
def api_bot_tracking_stop():
    bad = _require_bot_key()
    if bad:
        return jsonify(bad[0]), bad[1]
    bad = _bot_rate_limit('duty_tracking_stop', 'RATE_LIMIT_DUTY_TRACKING_STOP_PER_MINUTE', 60)
    if bad:
        return jsonify(bad[0]), bad[1]
    data = request.get_json(silent=True) or {}
    user_id = str(data.get('user_id') or '')
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    session_id = data.get('session_id')
    message_id = data.get('message_id')

    sess = None
    if session_id:
        sess = TrackingSession.query.filter_by(id=int(session_id), user_id=user_id).first()
    elif message_id:
        sess = TrackingSession.query.filter_by(user_id=user_id, message_id=int(message_id), ended_at=None).first()
    else:
        sess = TrackingSession.query.filter_by(user_id=user_id, ended_at=None).order_by(desc(TrackingSession.started_at)).first()

    if not sess or sess.ended_at is not None:
        return jsonify({'ok': True, 'message': 'no active session'}), 200

    sess.ended_at = _utcnow()
    sess.is_active = False

    # точки сессии
    points = TrackingPoint.query.filter_by(session_id=sess.id).order_by(TrackingPoint.ts.asc()).all()
    stops = _compute_stops(points)
    for st in stops:
        db.session.add(st)

    # svg snapshot
    tracks_dir = _ensure_tracks_dir()
    svg = _build_route_svg(points, stops)
    filename = f"tracks/track_{sess.id}.svg"
    abs_path = os.path.join(current_app.config.get('UPLOAD_FOLDER'), filename)
    # ensure parent
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, 'w', encoding='utf-8') as f:
        f.write(svg)
    sess.snapshot_path = filename

    summary = {
        'points': len(points),
        'stops': [{'lat': st.center_lat, 'lon': st.center_lon, 'duration_sec': st.duration_sec} for st in stops],
        'stationary_total_sec': int(sum((st.duration_sec or 0) for st in stops)),
    }
    sess.summary_json = json.dumps(summary, ensure_ascii=False)

    sh = _get_active_shift(user_id)
    _log_event(user_id, sh.id if sh else None, 'TRACKING_STOP', actor='user', payload={'session_id': sess.id, 'snapshot': filename, **summary})
    db.session.commit()

    broadcast_event_sync('tracking_stopped', {'user_id': user_id, 'shift_id': sh.id if sh else None, 'session_id': sess.id, 'snapshot_url': f"/uploads/{filename}"})
    return jsonify({'ok': True, 'session_id': sess.id, 'snapshot_url': f"/uploads/{filename}", 'summary': summary})



@bp.post('/api/duty/bot/sos')
def api_bot_sos():
    """Создать SOS по явной координате (бот прислал геометку)."""
    bad = _require_bot_key()
    if bad:
        return jsonify(bad[0]), bad[1]
    bad = _bot_rate_limit('duty_sos', 'RATE_LIMIT_DUTY_SOS_PER_MINUTE', 30)
    if bad:
        return jsonify(bad[0]), bad[1]
    data = request.get_json(silent=True) or {}
    user_id = str(data.get('user_id') or '')
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400

    unit = (data.get('unit_label') or '').strip()[:64] or None
    lat = data.get('lat'); lon = data.get('lon')
    if lat is None or lon is None:
        return jsonify({'error': 'lat/lon required'}), 400

    sh = _get_or_create_active_shift(user_id, unit_label=unit)

    alert = SosAlert(
        user_id=user_id,
        shift_id=sh.id if sh else None,
        session_id=data.get('session_id'),
        unit_label=unit or (sh.unit_label if sh else None),
        created_at=_utcnow(),
        status='open',
        lat=float(lat),
        lon=float(lon),
        accuracy_m=data.get('accuracy_m'),
        note=(data.get('note') or '')[:256] or None,
    )
    db.session.add(alert)
    db.session.flush()

    _log_event(user_id, sh.id if sh else None, 'SOS_CREATED', actor='user', payload={'sos_id': alert.id, 'lat': alert.lat, 'lon': alert.lon})
    db.session.commit()

    broadcast_event_sync('sos_created', alert.to_dict())
    return jsonify({'ok': True, 'sos_id': alert.id})


@bp.post('/api/duty/bot/sos/last')
def api_bot_sos_last():
    """Создать SOS по последней известной точке (из live или истории)."""
    bad = _require_bot_key()
    if bad:
        return jsonify(bad[0]), bad[1]
    bad = _bot_rate_limit('duty_sos_last', 'RATE_LIMIT_DUTY_SOS_PER_MINUTE', 30)
    if bad:
        return jsonify(bad[0]), bad[1]
    data = request.get_json(silent=True) or {}
    user_id = str(data.get('user_id') or '')
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    unit = (data.get('unit_label') or '').strip()[:64] or None

    last = _get_last_location(user_id)
    if not last:
        return jsonify({'error': 'no_last_location', 'need_location': True}), 409

    sh = _get_or_create_active_shift(user_id, unit_label=unit)

    alert = SosAlert(
        user_id=user_id,
        shift_id=sh.id if sh else None,
        session_id=last.get('session_id'),
        unit_label=unit or (sh.unit_label if sh else None),
        created_at=_utcnow(),
        status='open',
        lat=float(last.get('lat')),
        lon=float(last.get('lon')),
        accuracy_m=last.get('accuracy_m'),
        note=(data.get('note') or '')[:256] or None,
    )
    db.session.add(alert)
    db.session.flush()

    _log_event(user_id, sh.id if sh else None, 'SOS_CREATED', actor='user', payload={'sos_id': alert.id, 'lat': alert.lat, 'lon': alert.lon, 'source': 'last'})
    db.session.commit()

    broadcast_event_sync('sos_created', alert.to_dict())
    return jsonify({'ok': True, 'sos_id': alert.id, 'used_last': True, 'last': last})


@bp.post('/api/duty/bot/break/request')
def api_bot_break_request():
    bad = _require_bot_key()
    if bad:
        return jsonify(bad[0]), bad[1]
    bad = _bot_rate_limit('duty_break_request', 'RATE_LIMIT_DUTY_BREAK_PER_MINUTE', 60)
    if bad:
        return jsonify(bad[0]), bad[1]
    data = request.get_json(silent=True) or {}
    user_id = str(data.get('user_id') or '')
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    duration = int(data.get('duration_min') or 30)
    duration = max(5, min(duration, 180))
    unit = (data.get('unit_label') or '').strip()[:64] or None

    sh = _get_or_create_active_shift(user_id, unit_label=unit)
    br = BreakRequest(
        user_id=user_id,
        shift_id=sh.id,
        requested_at=_utcnow(),
        duration_min=duration,
        status='requested',
        due_notified=False,
    )
    db.session.add(br)
    db.session.flush()
    _log_event(user_id, sh.id, 'BREAK_REQUEST', actor='user', payload={'break_id': br.id, 'duration_min': duration})
    db.session.commit()

    broadcast_event_sync('break_requested', {'user_id': user_id, 'shift_id': sh.id, 'break_id': br.id, 'duration_min': duration, 'unit_label': sh.unit_label})
    return jsonify({'ok': True, 'break_id': br.id})


@bp.post('/api/duty/bot/shift/set_unit')
def api_bot_set_unit():
    bad = _require_bot_key()
    if bad:
        return jsonify(bad[0]), bad[1]
    bad = _bot_rate_limit('duty_set_unit', 'RATE_LIMIT_DUTY_SETUNIT_PER_MINUTE', 60)
    if bad:
        return jsonify(bad[0]), bad[1]
    data = request.get_json(silent=True) or {}
    user_id = str(data.get('user_id') or '')
    unit = (data.get('unit_label') or '').strip()[:64]
    if not user_id or not unit:
        return jsonify({'error': 'user_id and unit_label required'}), 400
    sh = _get_or_create_active_shift(user_id, unit_label=unit)
    sh.unit_label = unit
    _log_event(user_id, sh.id, 'SET_UNIT', actor='user', payload={'unit_label': unit})
    db.session.commit()
    return jsonify({'ok': True, 'shift_id': sh.id, 'unit_label': sh.unit_label})


# -------------------------
# Admin API endpoints
# -------------------------

@bp.get('/api/duty/admin/dashboard')
def api_admin_dashboard():
    require_admin()
    now = _utcnow()
    shifts = DutyShift.query.filter(DutyShift.ended_at == None).order_by(desc(DutyShift.started_at)).all()  # noqa: E711
    res_shifts = []
    for sh in shifts:
        # last point: prefer last TrackingPoint (has accuracy_m). Fallback to session.last_*.
        sess = TrackingSession.query.filter_by(user_id=sh.user_id, ended_at=None).order_by(desc(TrackingSession.started_at)).first()
        last = None
        last_ts = None

        if sess:
            lp = _select_display_point(sess.id, now)
            if lp and lp.lat is not None and lp.lon is not None:
                last = {
                    'lat': lp.lat,
                    'lon': lp.lon,
                    'ts': lp.ts.isoformat() if lp.ts else None,
                    'session_id': lp.session_id,
                    'accuracy_m': lp.accuracy_m,
                }
                last_ts = lp.ts
                meta = _last_meta_fields(lp)
                if meta and last:
                    last.update(meta)
            elif sess.last_lat is not None and sess.last_lon is not None:
                last = {
                    'lat': sess.last_lat,
                    'lon': sess.last_lon,
                    'ts': sess.last_at.isoformat() if sess.last_at else None,
                    'session_id': sess.id,
                    'accuracy_m': None,
                }
                last_ts = sess.last_at

        if not last:
            lp = TrackingPoint.query.filter_by(user_id=sh.user_id).order_by(desc(TrackingPoint.ts)).first()
            if lp and lp.lat is not None and lp.lon is not None:
                last = {
                    'lat': lp.lat,
                    'lon': lp.lon,
                    'ts': lp.ts.isoformat() if lp.ts else None,
                    'session_id': lp.session_id,
                    'accuracy_m': lp.accuracy_m,
                }
                last_ts = lp.ts
                meta = _last_meta_fields(lp)
                if meta and last:
                    last.update(meta)
        br = BreakRequest.query.filter_by(user_id=sh.user_id).filter(BreakRequest.status.in_(['requested','started'])).order_by(desc(BreakRequest.requested_at)).first()
        # last health (Android) if exists
        # Важно: у одного user_id может быть несколько устройств (перепривязка/ротация).
        # Поэтому берём health именно для "актуального" устройства (по last_seen_at),
        # иначе Dashboard может показывать старую health/"нет связи" при наличии новых точек.
        dev = (
            TrackerDevice.query
            .filter(TrackerDevice.user_id == sh.user_id, TrackerDevice.is_revoked == False)  # noqa: E712
            .order_by(desc(TrackerDevice.last_seen_at), desc(TrackerDevice.created_at))
            .first()
        )
        h = TrackerDeviceHealth.query.filter_by(device_id=dev.public_id).first() if dev else (
            TrackerDeviceHealth.query.filter_by(user_id=sh.user_id).order_by(desc(TrackerDeviceHealth.updated_at)).first()
        )
        health = h.to_dict() if h else None
        health_age_sec = None
        if h and h.updated_at:
            try:
                health_age_sec = int((now - h.updated_at).total_seconds())
            except Exception:
                health_age_sec = None

        heartbeat_ts = None
        try:
            if dev and dev.last_seen_at:
                heartbeat_ts = dev.last_seen_at
        except Exception:
            heartbeat_ts = None
        try:
            if h and h.updated_at:
                heartbeat_ts = (heartbeat_ts if (heartbeat_ts and heartbeat_ts >= h.updated_at) else h.updated_at)
        except Exception:
            pass

        device_status = _compute_device_status(now, last_ts, heartbeat_ts)

        res_shifts.append({
            'shift_id': sh.id,
            'user_id': sh.user_id,
            'unit_label': sh.unit_label,
            'started_at': sh.started_at.isoformat() if sh.started_at else None,
            'last': last,
            'tracking_active': bool(sess and sess.ended_at is None),
            'break': br.to_dict() if br else None,
            'health': health,
            'health_age_sec': health_age_sec,
            'device_status': device_status,
            'kpi_5m': _kpi_5m_for_session(last.get('session_id') if last else None, now),
        })

    breaks = BreakRequest.query.filter(BreakRequest.status.in_(['requested','started'])).order_by(desc(BreakRequest.requested_at)).all()
    res_breaks = [b.to_dict() for b in breaks]

    sos_rows = SosAlert.query.filter(SosAlert.status.in_(['open','acked'])).order_by(desc(SosAlert.created_at)).limit(50).all()
    res_sos = [r.to_dict() for r in sos_rows]

    return jsonify({'server_time': now.isoformat(), 'active_shifts': res_shifts, 'breaks': res_breaks, 'sos_active': res_sos, 'sos_active_count': len(res_sos)})


@bp.get('/api/duty/admin/shift/<int:shift_id>/detail')
def api_admin_shift_detail(shift_id: int):
    """Детали смены для правой карточки (командный центр)."""
    require_admin()
    now = _utcnow()
    sh = DutyShift.query.get(shift_id)
    if not sh:
        return jsonify({'error': 'not found'}), 404

    # последние сессии трекинга по этой смене (или по user_id, если shift_id не проставлен)
    sess_q = TrackingSession.query.filter(
        (TrackingSession.shift_id == sh.id) | ((TrackingSession.shift_id == None) & (TrackingSession.user_id == sh.user_id))
    ).order_by(desc(TrackingSession.started_at))  # noqa: E711
    sessions = sess_q.limit(15).all()
    active_sess = TrackingSession.query.filter_by(user_id=sh.user_id, ended_at=None).order_by(desc(TrackingSession.started_at)).first()

    # последняя точка
    last = None
    last_ts = None
    last_session_id = None
    if active_sess:
        lp = _select_display_point(active_sess.id, now)
        if lp and lp.lat is not None and lp.lon is not None:
            last = {
                'lat': lp.lat,
                'lon': lp.lon,
                'ts': lp.ts.isoformat() if lp.ts else None,
                'accuracy_m': lp.accuracy_m,
            }
            meta = _last_meta_fields(lp)
            if meta and last:
                last.update(meta)
            last_ts = lp.ts
            last_session_id = lp.session_id
        elif active_sess.last_lat is not None and active_sess.last_lon is not None:
            last = {
                'lat': active_sess.last_lat,
                'lon': active_sess.last_lon,
                'ts': active_sess.last_at.isoformat() if active_sess.last_at else None,
                'accuracy_m': None,
            }
            last_ts = active_sess.last_at
            last_session_id = active_sess.id

    if not last:
        lp = TrackingPoint.query.filter_by(user_id=sh.user_id).order_by(desc(TrackingPoint.ts)).first()
        if lp and lp.lat is not None and lp.lon is not None:
            last = {
                'lat': lp.lat,
                'lon': lp.lon,
                'ts': lp.ts.isoformat() if lp.ts else None,
                'accuracy_m': lp.accuracy_m,
            }
            meta = _last_meta_fields(lp)
            if meta and last:
                last.update(meta)
            last_ts = lp.ts
            last_session_id = lp.session_id

    # события смены (последние 200)
    ev = DutyEvent.query.filter_by(shift_id=sh.id).order_by(DutyEvent.ts.asc()).limit(200).all()

    # актуальный обед
    br = BreakRequest.query.filter_by(user_id=sh.user_id).filter(BreakRequest.status.in_(['requested','started'])).order_by(desc(BreakRequest.requested_at)).first()

    # SOS (последний / активный)
    sos_active = SosAlert.query.filter_by(user_id=sh.user_id).filter(SosAlert.status.in_(['open','acked'])).order_by(desc(SosAlert.created_at)).first()
    sos_last = SosAlert.query.filter_by(user_id=sh.user_id).order_by(desc(SosAlert.created_at)).first()

    # last health (Android) if exists
    # См. комментарий в dashboard: у одного user_id может быть несколько устройств.
    dev = (
        TrackerDevice.query
        .filter(TrackerDevice.user_id == sh.user_id, TrackerDevice.is_revoked == False)  # noqa: E712
        .order_by(desc(TrackerDevice.last_seen_at), desc(TrackerDevice.created_at))
        .first()
    )
    h = TrackerDeviceHealth.query.filter_by(device_id=dev.public_id).first() if dev else (
        TrackerDeviceHealth.query.filter_by(user_id=sh.user_id).order_by(desc(TrackerDeviceHealth.updated_at)).first()
    )
    health = h.to_dict() if h else None
    health_age_sec = None
    if h and h.updated_at:
        try:
            health_age_sec = int((now - h.updated_at).total_seconds())
        except Exception:
            health_age_sec = None

    heartbeat_ts = None
    try:
        if dev and dev.last_seen_at:
            heartbeat_ts = dev.last_seen_at
    except Exception:
        heartbeat_ts = None
    try:
        if h and h.updated_at:
            heartbeat_ts = (heartbeat_ts if (heartbeat_ts and heartbeat_ts >= h.updated_at) else h.updated_at)
    except Exception:
        pass

    device_status = _compute_device_status(now, last_ts, heartbeat_ts)

    age_sec = None
    if last_ts:
        try:
            age_sec = int((now - last_ts).total_seconds())
        except Exception:
            age_sec = None

    return jsonify({
        'shift': sh.to_dict(),
        'last': last,
        'last_session_id': last_session_id,
        'last_age_sec': age_sec,
        'tracking_active': bool(active_sess and active_sess.ended_at is None),
        'active_session': active_sess.to_dict() if active_sess else None,
        'sessions': [s.to_dict() for s in sessions],
        'events': [e.to_dict() for e in ev],
        'break': br.to_dict() if br else None,
        'health': health,
        'health_age_sec': health_age_sec,
        'device_status': device_status,
        'kpi_5m': _kpi_5m_for_session(last_session_id, now),
        'sos_active': sos_active.to_dict() if sos_active else None,
        'sos_last': sos_last.to_dict() if sos_last else None,
    })

@bp.get('/api/duty/admin/sos/active')
def api_admin_sos_active():
    require_admin()
    rows = SosAlert.query.filter(SosAlert.status.in_(['open', 'acked'])).order_by(desc(SosAlert.created_at)).limit(200).all()
    return jsonify([r.to_dict() for r in rows])


@bp.post('/api/duty/admin/sos/<int:sos_id>/ack')
def api_admin_sos_ack(sos_id: int):
    require_admin()
    row = SosAlert.query.get(sos_id)
    if not row:
        return jsonify({'error': 'not found'}), 404
    if row.status == 'closed':
        return jsonify({'ok': True, 'sos': row.to_dict()})
    if row.status != 'acked':
        row.status = 'acked'
        row.acked_at = _utcnow()
        row.acked_by = (request.args.get('by') or '').strip() or None
        _log_event(row.user_id, row.shift_id, 'SOS_ACKED', actor='admin', payload={'sos_id': row.id})
        _create_notification(row.user_id, 'sos_acked', "✅ SOS принят оператором. Держитесь, помощь в пути.", {'sos_id': row.id})
        db.session.commit()
        broadcast_event_sync('sos_acked', row.to_dict())
    return jsonify({'ok': True, 'sos': row.to_dict()})


@bp.post('/api/duty/admin/sos/<int:sos_id>/close')
def api_admin_sos_close(sos_id: int):
    require_admin()
    row = SosAlert.query.get(sos_id)
    if not row:
        return jsonify({'error': 'not found'}), 404
    if row.status != 'closed':
        row.status = 'closed'
        row.closed_at = _utcnow()
        row.closed_by = (request.args.get('by') or '').strip() or None
        _log_event(row.user_id, row.shift_id, 'SOS_CLOSED', actor='admin', payload={'sos_id': row.id})
        _create_notification(row.user_id, 'sos_closed', "🟢 SOS закрыт оператором. Спасибо за подтверждение.", {'sos_id': row.id})
        db.session.commit()
        broadcast_event_sync('sos_closed', row.to_dict())
    return jsonify({'ok': True, 'sos': row.to_dict()})



@bp.get('/api/duty/admin/tracking/<int:session_id>')
def api_admin_tracking(session_id: int):
    require_admin()
    sess = TrackingSession.query.get(session_id)
    if not sess:
        return jsonify({'error': 'not found'}), 404
    points = TrackingPoint.query.filter_by(session_id=session_id).order_by(TrackingPoint.ts.asc()).all()
    stops = TrackingStop.query.filter_by(session_id=session_id).order_by(TrackingStop.start_ts.asc()).all()
    return jsonify({
        'session': sess.to_dict(),
        'points': [p.to_dict() for p in points],
        'stops': [s.to_dict() for s in stops],
        'snapshot_url': f"/uploads/{sess.snapshot_path}" if sess.snapshot_path else None,
    })


@bp.post('/api/duty/admin/breaks/<int:break_id>/approve')
def api_admin_break_approve(break_id: int):
    require_admin()
    br = BreakRequest.query.get(break_id)
    if not br:
        return jsonify({'error': 'not found'}), 404
    if br.status != 'requested':
        return jsonify({'ok': True, 'status': br.status})
    br.status = 'started'
    br.started_at = _utcnow()
    br.ends_at = br.started_at + timedelta(minutes=int(br.duration_min or 30))
    br.approved_by = (request.args.get('by') or '').strip() or None

    _log_event(br.user_id, br.shift_id, 'BREAK_START', actor='admin', payload={'break_id': br.id, 'ends_at': br.ends_at.isoformat()})
    _create_notification(br.user_id, 'break_started', f"🍽 Обед подтверждён. Длительность: {br.duration_min} мин. Конец: {br.ends_at.strftime('%H:%M:%S')} (UTC).", {'break_id': br.id, 'ends_at': br.ends_at.isoformat()})
    db.session.commit()

    broadcast_event_sync('break_started', {'user_id': br.user_id, 'shift_id': br.shift_id, 'break_id': br.id, 'ends_at': br.ends_at.isoformat()})
    return jsonify({'ok': True, 'break': br.to_dict()})


@bp.post('/api/duty/admin/breaks/<int:break_id>/end')
def api_admin_break_end(break_id: int):
    require_admin()
    br = BreakRequest.query.get(break_id)
    if not br:
        return jsonify({'error': 'not found'}), 404
    if br.status == 'ended':
        return jsonify({'ok': True, 'break': br.to_dict()})
    br.status = 'ended'
    br.ended_at = _utcnow()
    _log_event(br.user_id, br.shift_id, 'BREAK_END', actor='admin', payload={'break_id': br.id})
    _create_notification(br.user_id, 'break_ended', "✅ Обед завершён оператором. Возвращайтесь к несению службы.", {'break_id': br.id})
    db.session.commit()

    broadcast_event_sync('break_ended', {'user_id': br.user_id, 'shift_id': br.shift_id, 'break_id': br.id})
    return jsonify({'ok': True, 'break': br.to_dict()})


# -------------------------
# Bot notification polling endpoints
# -------------------------

@bp.get('/api/duty/notify_targets')
def api_notify_targets():
    # не требуем админа: это вызывается ботом с X-API-KEY
    bad = _require_bot_key()
    if bad:
        return jsonify(bad[0]), bad[1]
    rows = DutyNotification.query.filter_by(acked=False).order_by(DutyNotification.created_at.asc()).all()
    # вернём уникальные user_id с количеством
    counts: Dict[str, int] = {}
    for r in rows:
        counts[r.user_id] = counts.get(r.user_id, 0) + 1
    return jsonify([{'user_id': uid, 'count': cnt} for uid, cnt in counts.items()])


@bp.get('/api/duty/<user_id>/pending')
def api_user_pending(user_id: str):
    bad = _require_bot_key()
    if bad:
        return jsonify(bad[0]), bad[1]
    rows = DutyNotification.query.filter_by(user_id=str(user_id), acked=False).order_by(DutyNotification.created_at.asc()).limit(20).all()
    return jsonify([r.to_dict() for r in rows])


@bp.post('/api/duty/<user_id>/ack')
def api_user_ack(user_id: str):
    bad = _require_bot_key()
    if bad:
        return jsonify(bad[0]), bad[1]
    data = request.get_json(silent=True) or {}
    ids = data.get('ids') or []
    if not isinstance(ids, list):
        ids = []
    now = _utcnow()
    q = DutyNotification.query.filter_by(user_id=str(user_id), acked=False)
    if ids:
        q = q.filter(DutyNotification.id.in_([int(x) for x in ids if str(x).isdigit()]))
    rows = q.all()
    for r in rows:
        r.acked = True
        r.acked_at = now
    db.session.commit()
    return jsonify({'ok': True, 'acked': len(rows)})


# -------------------------
# Scheduler tick (optional)
# -------------------------

def duty_scheduler_tick() -> None:
    """Проверка обедов на истечение, рассылает событие админу."""
    now = _utcnow()
    due = BreakRequest.query.filter_by(status='started', due_notified=False).filter(BreakRequest.ends_at != None).all()  # noqa: E711
    changed = 0
    for br in due:
        if br.ends_at and br.ends_at <= now:
            br.due_notified = True
            _log_event(br.user_id, br.shift_id, 'BREAK_DUE', actor='system', payload={'break_id': br.id})
            # админу — WS
            broadcast_event_sync('break_due', {'user_id': br.user_id, 'shift_id': br.shift_id, 'break_id': br.id})
            # наряду — мягко
            _create_notification(br.user_id, 'break_due', "⏱ Время обеда истекло. Ожидайте отметки оператора.", {'break_id': br.id})
            changed += 1
    if changed:
        db.session.commit()