"""Tracker API (Android):
- pairing по одноразовому коду
- device token auth
- start/stop смены
- points пачками
- профиль устройства

Важно:
  Это модуль "приложения". Telegram-бот использует /api/duty/bot/*.
"""

from __future__ import annotations

import json
import uuid
import re
from urllib.parse import quote
import os
import secrets
import time
import hashlib
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple, List

from pydantic import ValidationError
from flask import request, jsonify, current_app, g, abort, Response

from . import bp
from ..extensions import db
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
from ..helpers import require_admin, get_current_admin
from ..security.api_keys import require_bot_api_key
from ..audit.logger import log_admin_action
from ..integrations.telegram_sender import send_dutytracker_connect_button
from ..sockets import broadcast_event_sync
from .alerting import tracker_alerts_tick
from ..schemas import TelemetryCreateSchema
from ..models import (
    TrackerPairCode,
    TrackerBootstrapToken,
    TrackerConnectRequest,
    TrackerDevice,
    TrackerDeviceHealth,
    TrackerDeviceHealthLog,
    TrackerFingerprintSample,
    TrackerRadioTile,
    TrackerRadioAPStat,
    TrackerRadioCellStat,
    DutyShift,
    TrackingSession,
    TrackingPoint,
    SosAlert,
    TrackerAlert,
    TrackerAdminAudit,
    ServiceAccess,
)


# -------------------------
# request id
# -------------------------

@bp.before_app_request
def _ensure_request_id():
    rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    g.request_id = rid

# -------------------------
# small utils
# -------------------------

def _utcnow() -> datetime:
    return datetime.utcnow()

def _parse_ts_arg(v: str | None) -> datetime | None:
    """Parse timestamp from query args.
    Supports:
      - epoch seconds (e.g., 1730000000)
      - epoch milliseconds (e.g., 1730000000000)
      - ISO 8601 (e.g., 2026-01-02T10:15:00 or 2026-01-02T10:15:00Z)
    Returns naive UTC datetime (no tzinfo).
    """
    if not v:
        return None
    s = str(v).strip()
    if not s:
        return None
    # numeric epoch
    if re.fullmatch(r"\d{9,16}", s):
        try:
            n = int(s)
            # heuristics: ms if >= 1e12 or length >= 13
            if n >= 10**12:
                return datetime.utcfromtimestamp(n / 1000.0)
            return datetime.utcfromtimestamp(float(n))
        except Exception:
            return None
    # iso 8601
    try:
        ss = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(ss)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except Exception:
        return None


def _get_time_range_from_args() -> tuple[datetime | None, datetime | None]:
    """Returns (from_dt, to_dt) from query args 'from'/'to' (or 'from_ts'/'to_ts').
    If only one side is provided, returns it and None for the other side.
    If both provided and swapped, auto-swaps.
    """
    frm = _parse_ts_arg(request.args.get("from") or request.args.get("from_ts"))
    to = _parse_ts_arg(request.args.get("to") or request.args.get("to_ts"))
    if frm and to and to < frm:
        frm, to = to, frm
    return frm, to

def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def _client_ip() -> str:
    return request.headers.get("X-Forwarded-For", request.remote_addr) or "unknown"

# -------------------------
# API response helpers (tracker contract v1)
# -------------------------
TRACKER_SCHEMA_VERSION = 1

def _ok(payload: Optional[Dict[str, Any]] = None, **kwargs):
    base: Dict[str, Any] = {
        'ok': True,
        'schema_version': TRACKER_SCHEMA_VERSION,
        'server_time': _utcnow().isoformat() + 'Z',
        'request_id': getattr(g, 'request_id', None),
    }
    if payload:
        base.update(payload)
    if kwargs:
        base.update(kwargs)
    resp = jsonify(base)
    resp.headers['X-Request-ID'] = getattr(g, 'request_id', '')
    return resp, 200

def _err(code: str, message: str, status: int = 400, *, details: Optional[Dict[str, Any]] = None, **kwargs):
    base: Dict[str, Any] = {
        'ok': False,
        'code': code,
        'error': message,
        'schema_version': TRACKER_SCHEMA_VERSION,
        'server_time': _utcnow().isoformat() + 'Z',
        'request_id': getattr(g, 'request_id', None),
    }
    if details is not None:
        base['details'] = details
    if kwargs:
        base.update(kwargs)
    resp = jsonify(base)
    resp.headers['X-Request-ID'] = getattr(g, 'request_id', '')
    return resp, status


def _audit(action: str, device_id: Optional[str] = None, user_id: Optional[str] = None, payload: Optional[Dict[str, Any]] = None) -> None:
    """Пишем аудит действий диспетчера по трекеру.

    Важно: не должен ломать основную логику, поэтому здесь best-effort.
    """
    try:
        admin = get_current_admin()
        actor = None
        if admin:
            actor = getattr(admin, 'username', None) or getattr(admin, 'login', None)
        actor = actor or (request.args.get('by') or '').strip() or None

        row = TrackerAdminAudit(
            actor=actor,
            action=action,
            device_id=device_id,
            user_id=user_id,
            payload_json=json.dumps(payload, ensure_ascii=False) if payload else None,
        )
        db.session.add(row)
        db.session.commit()
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass

# -------------------------
# naive in-memory anti-bruteforce for /pair (dev-friendly)
# -------------------------
_PAIR_IP_WINDOW_SEC = 60
_PAIR_IP_MAX = 20
_PAIR_CODE_WINDOW_SEC = 60
_PAIR_CODE_MAX = 10

_pair_ip_bucket: Dict[str, List[float]] = {}
_pair_code_bucket: Dict[str, List[float]] = {}

def _rate_limit_pair(ip: str, code_hash: str) -> Optional[Tuple[Any, int]]:
    now = time.time()

    def push(bucket: Dict[str, List[float]], key: str, window: int, maxn: int) -> bool:
        arr = bucket.get(key) or []
        arr = [t for t in arr if (now - t) <= window]
        arr.append(now)
        bucket[key] = arr
        return len(arr) <= maxn

    if not push(_pair_ip_bucket, ip, _PAIR_IP_WINDOW_SEC, _PAIR_IP_MAX):
        return _err('rate_limited_ip', 'Too many attempts. Try later.', 429)
    if not push(_pair_code_bucket, code_hash, _PAIR_CODE_WINDOW_SEC, _PAIR_CODE_MAX):
        return _err('rate_limited_code', 'Too many attempts for this code. Try later.', 429)
    return None

# -------------------------
# Rate limits (in-memory, DEV-friendly)
# -------------------------
# NOTE: This is process-local. For multi-worker/prod use, prefer Redis / reverse-proxy rate limiting.
from ..security.rate_limit import check_rate_limit

# NOTE:
# Ранее здесь был полностью process-local rate limit через списки таймстэмпов.
# Для prod-масштабирования (несколько воркеров) переключаемся на общий helper
# check_rate_limit(..) с поддержкой Redis (если задан REDIS_URL),
# а при отсутствии Redis остаётся best-effort in-memory.

_dev_bucket_points: Dict[str, List[float]] = {}  # fallback only
_dev_bucket_health: Dict[str, List[float]] = {}  # fallback only
_dev_bucket_sos: Dict[str, List[float]] = {}     # fallback only
_dev_bucket_fp: Dict[str, List[float]] = {}      # fallback only

_FP_WINDOW_SEC = 60
_POINTS_WINDOW_SEC = 60
_HEALTH_WINDOW_SEC = 60
_SOS_WINDOW_SEC = 300


def _rate_limit_device(bucket: Dict[str, List[float]], key: str, window_sec: int, maxn: int, *, code: str) -> Optional[Tuple[Any, int]]:
    now = time.time()
    arr = bucket.get(key) or []
    arr = [t for t in arr if (now - t) <= window_sec]
    arr.append(now)
    bucket[key] = arr
    if len(arr) > maxn:
        return _err('rate_limited', 'Too many requests', 429, details={'reason': code, 'window_sec': window_sec, 'max': maxn})
    return None


def _rl_points(dev: TrackerDevice) -> Optional[Tuple[Any, int]]:
    limit = int(current_app.config.get("RATE_LIMIT_TRACKER_POINTS_PER_MINUTE", 6000))
    try:
        ok, info = check_rate_limit("tracker_points", dev.public_id, limit=limit, window_seconds=_POINTS_WINDOW_SEC)
        if not ok:
            return _err('rate_limited', 'Too many point uploads', 429, details={"bucket": "tracker_points", "limit": limit, "window_sec": _POINTS_WINDOW_SEC, **info.to_headers()})
        return None
    except Exception:
        # Fallback to process-local limiter
        return _rate_limit_device(_dev_bucket_points, dev.public_id, _POINTS_WINDOW_SEC, limit, code='too_many_points')


def _rl_health(dev: TrackerDevice) -> Optional[Tuple[Any, int]]:
    limit = int(current_app.config.get("RATE_LIMIT_TRACKER_HEALTH_PER_MINUTE", 120))
    try:
        ok, info = check_rate_limit("tracker_health", dev.public_id, limit=limit, window_seconds=_HEALTH_WINDOW_SEC)
        if not ok:
            return _err('rate_limited', 'Too many health updates', 429, details={"bucket": "tracker_health", "limit": limit, "window_sec": _HEALTH_WINDOW_SEC, **info.to_headers()})
        return None
    except Exception:
        return _rate_limit_device(_dev_bucket_health, dev.public_id, _HEALTH_WINDOW_SEC, limit, code='too_many_health')


def _rl_sos(dev: TrackerDevice) -> Optional[Tuple[Any, int]]:
    limit = int(current_app.config.get("RATE_LIMIT_TRACKER_SOS_PER_5MIN", 3))
    try:
        ok, info = check_rate_limit("tracker_sos", dev.public_id, limit=limit, window_seconds=_SOS_WINDOW_SEC)
        if not ok:
            return _err('rate_limited', 'Too many SOS events', 429, details={"bucket": "tracker_sos", "limit": limit, "window_sec": _SOS_WINDOW_SEC, **info.to_headers()})
        return None
    except Exception:
        return _rate_limit_device(_dev_bucket_sos, dev.public_id, _SOS_WINDOW_SEC, limit, code='too_many_sos')


def _rl_fp(dev: TrackerDevice) -> Optional[Tuple[Any, int]]:
    limit = int(current_app.config.get("RATE_LIMIT_TRACKER_FINGERPRINTS_PER_MINUTE", 60))
    try:
        ok, info = check_rate_limit("tracker_fingerprints", dev.public_id, limit=limit, window_seconds=_FP_WINDOW_SEC)
        if not ok:
            return _err('rate_limited', 'Too many fingerprint uploads', 429, details={"bucket": "tracker_fingerprints", "limit": limit, "window_sec": _FP_WINDOW_SEC, **info.to_headers()})
        return None
    except Exception:
        return _rate_limit_device(_dev_bucket_fp, dev.public_id, _FP_WINDOW_SEC, limit, code='too_many_fingerprints')

def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance in meters between two WGS84 points."""
    from math import radians, sin, cos, asin, sqrt
    R = 6371000.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    return 2 * R * asin(sqrt(a))






# -------------------------
# Auth
# -------------------------

def _require_device() -> Tuple[Optional[TrackerDevice], Optional[Tuple[Any, int]]]:
    """Return (device, None) or (None, (flask_response, status))."""
    tok = request.headers.get("X-DEVICE-TOKEN")
    if not tok:
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            tok = auth.split(" ", 1)[1].strip()

    if not tok:
        return None, _err('missing_token', 'Missing device token', 401)

    h = _sha256_hex(tok)
    dev = TrackerDevice.query.filter_by(token_hash=h).first()
    if not dev:
        return None, _err('invalid_token', 'Invalid token', 403)

    if getattr(dev, 'is_revoked', False):
        # Best-effort: создаём алёрт и шлём в UI, чтобы диспетчер видел попытки отозванного устройства.
        try:
            row = TrackerAlert.query.filter_by(device_id=dev.public_id, user_id=dev.user_id, kind='revoked_device_traffic', is_active=True).order_by(TrackerAlert.created_at.desc()).first()
            if not row:
                row = TrackerAlert(
                    device_id=dev.public_id,
                    user_id=dev.user_id,
                    kind='revoked_device_traffic',
                    severity='crit',
                    message='Revoked device tried to send data',
                    payload_json=json.dumps({'path': request.path, 'ip': request.remote_addr}, ensure_ascii=False),
                    is_active=True,
                )
                db.session.add(row)
            else:
                row.updated_at = _utcnow()
            db.session.commit()
            broadcast_event_sync('tracker_alert', row.to_dict())
        except Exception:
            db.session.rollback()
        return None, _err('revoked_token', 'Token revoked', 403)


    dev.last_seen_at = _utcnow()
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()

    return dev, None


@bp.post("/api/tracker/health")
def api_health():
    """Health/heartbeat от приложения.

    Это короткий пакет состояния, который помогает диспетчеру понимать,
    почему трекинг "не идёт": батарея, сеть, GPS, очередь точек, ошибка.

    Пример тела:
      {
        "battery_pct": 72,
        "is_charging": false,
        "net": "wifi"|"cell"|"none",
        "gps": "ok"|"off"|"denied",
        "accuracy_m": 9.2,
        "queue_size": 14,
        "tracking_on": true,
        "last_send_at": "2025-12-23T12:31:05Z",
        "last_error": "...",
        "app_version": "1.2",
        "device_model": "Xiaomi ...",
        "os_version": "13",
        "extra": {...}
      }
    """
    dev, err = _require_device()
    if err:
        return err

    rl = _rl_health(dev)
    if rl:
        return rl

    data = request.get_json(silent=True) or {}

    def _int(v):
        try:
            return int(v) if v is not None else None
        except Exception:
            return None

    def _float(v):
        try:
            return float(v) if v is not None else None
        except Exception:
            return None

    def _bool(v):
        if v is None:
            return None
        if isinstance(v, bool):
            return v
        s = str(v).strip().lower()
        if s in ("1", "true", "yes", "y", "on"):
            return True
        if s in ("0", "false", "no", "n", "off"):
            return False
        return None

    def _dt(v):
        if not v:
            return None
        try:
            if isinstance(v, (int, float)):
                return datetime.utcfromtimestamp(float(v)/1000.0 if float(v) > 10_000_000_000 else float(v))
            return datetime.fromisoformat(str(v).replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            return None

    row = TrackerDeviceHealth.query.filter_by(device_id=dev.public_id).first()
    if not row:
        row = TrackerDeviceHealth(device_id=dev.public_id, user_id=dev.user_id)
        db.session.add(row)

    row.user_id = dev.user_id
    row.updated_at = _utcnow()

    row.battery_pct = _int(data.get("battery_pct"))
    row.is_charging = _bool(data.get("is_charging"))

    row.net = (data.get("net") or "").strip()[:16] or None
    row.gps = (data.get("gps") or "").strip()[:16] or None

    row.accuracy_m = _float(data.get("accuracy_m"))
    row.queue_size = _int(data.get("queue_size"))
    row.tracking_on = _bool(data.get("tracking_on"))

    row.last_send_at = _dt(data.get("last_send_at"))
    if row.last_send_at is None:
        # Если клиент не прислал last_send_at, считаем что "последняя отправка" = последний heartbeat.
        row.last_send_at = row.updated_at

    row.last_error = (data.get("last_error") or "").strip()[:256] or None

    row.app_version = (data.get("app_version") or "").strip()[:32] or None
    row.device_model = (data.get("device_model") or "").strip()[:64] or None
    row.os_version = (data.get("os_version") or "").strip()[:32] or None

    extra = data.get("extra")
    try:
        row.extra_json = json.dumps(extra, ensure_ascii=False) if isinstance(extra, dict) else None
    except Exception:
        row.extra_json = None

    # Пишем "последнее состояние" + при необходимости добавляем запись в лог.
    # Лог пишем не чаще чем раз в 30 секунд на устройство (чтобы не раздувать БД).
    try:
        last_log = TrackerDeviceHealthLog.query.filter_by(device_id=dev.public_id).order_by(TrackerDeviceHealthLog.ts.desc()).first()
    except Exception:
        last_log = None

    need_log = True
    if last_log and last_log.ts:
        try:
            need_log = (row.updated_at - last_log.ts).total_seconds() >= 30
        except Exception:
            need_log = True

    if need_log:
        lg = TrackerDeviceHealthLog(
            device_id=dev.public_id,
            user_id=dev.user_id,
            ts=row.updated_at,
            battery_pct=row.battery_pct,
            is_charging=row.is_charging,
            net=row.net,
            gps=row.gps,
            accuracy_m=row.accuracy_m,
            queue_size=row.queue_size,
            tracking_on=row.tracking_on,
            last_send_at=row.last_send_at,
            last_error=row.last_error,
            app_version=row.app_version,
            device_model=row.device_model,
            os_version=row.os_version,
            extra_json=row.extra_json,
        )
        db.session.add(lg)

    db.session.commit()

    # live update для диспетчера
    broadcast_event_sync("tracker_health", {
        "device_id": row.device_id,
        "user_id": row.user_id,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "battery_pct": row.battery_pct,
        "net": row.net,
        "gps": row.gps,
        "accuracy_m": row.accuracy_m,
        "queue_size": row.queue_size,
        "tracking_on": row.tracking_on,
        "last_send_at": row.last_send_at.isoformat() if row.last_send_at else None,
        "last_error": row.last_error,
    })

    return _ok({'health': row.to_dict()})



# -------------------------
# Fingerprint localization (MAX-2)
# -------------------------

def _wifi_vec(items: Any, *, k: int = 10) -> Dict[str, float]:
    """Return dict[bssid_hash] = rssi for top-K strongest APs."""
    out: Dict[str, float] = {}
    if not isinstance(items, list):
        return out
    tmp: List[Tuple[str, float]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        h = (it.get('bssid_hash') or '').strip()
        if not h:
            continue
        try:
            rssi = float(it.get('rssi'))
        except Exception:
            continue
        tmp.append((h, rssi))
    # rssi: closer to 0 => stronger
    tmp.sort(key=lambda x: x[1], reverse=True)
    for h, rssi in tmp[:k]:
        out[h] = rssi
    return out


def _cell_key(it: Dict[str, Any]) -> str:
    t = str(it.get('type') or '').strip().lower()
    if not t:
        t = 'cell'
    # CI + TAC/Pci are usually enough. Keep it stable.
    parts = [
        t,
        str(it.get('mcc') or ''),
        str(it.get('mnc') or ''),
        str(it.get('ci') or ''),
        str(it.get('tac') or it.get('lac') or ''),
        str(it.get('pci') or it.get('psc') or ''),
    ]
    return '|'.join(parts)


def _cell_vec(items: Any, *, k: int = 6) -> Dict[str, float]:
    """Return dict[cell_key] = strength(dbm/asu) for top-K."""
    out: Dict[str, float] = {}
    if not isinstance(items, list):
        return out
    tmp: List[Tuple[str, float]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        key = _cell_key(it)
        if not key:
            continue
        # prefer dbm, fallback to asu
        v = it.get('dbm')
        if v is None:
            v = it.get('asu')
        try:
            strength = float(v) if v is not None else 0.0
        except Exception:
            strength = 0.0
        tmp.append((key, strength))
    # for dbm, closer to 0 => stronger (note: dbm negative), for asu higher is stronger
    tmp.sort(key=lambda x: x[1], reverse=True)
    for key, strength in tmp[:k]:
        out[key] = strength
    return out


def _rssi_sim(a: float, b: float, *, scale: float = 30.0) -> float:
    """Similarity in [0..1] based on RSSI difference."""
    try:
        d = abs(float(a) - float(b))
    except Exception:
        return 0.0
    # exp falloff; scale ~30 dB
    return float(math.exp(-d / max(scale, 1.0)))


def _fp_similarity(w1: Dict[str, float], w2: Dict[str, float], c1: Dict[str, float], c2: Dict[str, float]) -> Tuple[float, Dict[str, Any]]:
    """Returns (score, details) for similarity between two fingerprints.

    Score is in [0..1].
    Details are used for MAX indoor diagnostics.
    """
    details: Dict[str, Any] = {
        "matches_wifi": 0,
        "matches_cell": 0,
        "overlap_wifi": 0.0,
        "overlap_cell": 0.0,
        "rssi_score": 0.0,
        "rssi_diff_avg_db": None,
        "score_raw": 0.0,
    }

    if not w1 or not w2:
        return 0.0, details

    inter = set(w1.keys()) & set(w2.keys())
    m = len(inter)
    details["matches_wifi"] = m
    if m == 0:
        return 0.0, details

    # AP overlap score
    overlap = m / float(max(1, min(len(w1), len(w2))))
    details["overlap_wifi"] = overlap

    # RSSI similarity + avg abs diff (db)
    rssi_score = 0.0
    abs_sum = 0.0
    for k in inter:
        d = abs(float(w1[k]) - float(w2[k]))
        abs_sum += d
        rssi_score += _rssi_sim(w1[k], w2[k], scale=25.0)
    rssi_score = rssi_score / float(max(1, m))
    details["rssi_score"] = rssi_score
    try:
        details["rssi_diff_avg_db"] = abs_sum / float(max(1, m))
    except Exception:
        details["rssi_diff_avg_db"] = None

    # Cell overlap (optional)
    cell_overlap = 0.0
    cm = 0
    if c1 and c2:
        inter_c = set(c1.keys()) & set(c2.keys())
        cm = len(inter_c)
        details["matches_cell"] = cm
        if cm:
            cell_overlap = cm / float(max(1, min(len(c1), len(c2))))
            details["overlap_cell"] = cell_overlap

    # Weighted blend (wifi dominates, cell helps when available)
    raw = 0.58 * overlap + 0.30 * rssi_score + 0.12 * cell_overlap
    details["score_raw"] = raw

    # Require enough matching APs for high confidence
    match_boost = min(1.0, m / 6.0)
    score = raw * (0.55 + 0.45 * match_boost)

    # clamp
    if score < 0:
        score = 0.0
    if score > 1:
        score = 1.0
    return score, details



def _localize_by_fingerprint(dev: TrackerDevice, wifi_items: list[dict], cell_items: list[dict]) -> Optional[Dict[str, Any]]:
    """Best-effort indoor localization using device's own anchor fingerprints.

    MAX-4 (anchoring/calibration):
    - use only "train" anchors with decent GNSS quality
    - score with wifi overlap + RSSI similarity + (optional) cell overlap
    - cluster anchors by location grid to reduce noise
    - return rich diagnostics for UI
    """
    try:
        w = _wifi_vec(wifi_items, k=10)
        c = _cell_vec(cell_items, k=6)
        if len(w) < 3:
            return None

        # tuning knobs (env/config)
        try:
            max_anchor_acc = float(current_app.config.get('MAX_ANCHOR_MAX_GNSS_ACC_M', 80))
        except Exception:
            max_anchor_acc = 80.0
        try:
            min_wifi_matches = int(current_app.config.get('MAX_ANCHOR_MIN_WIFI_MATCHES', 3))
        except Exception:
            min_wifi_matches = 3
        try:
            min_score = float(current_app.config.get('MAX_ANCHOR_MIN_SCORE', 0.55))
        except Exception:
            min_score = 0.55


        cutoff = _utcnow() - timedelta(days=30)
        anchors = (
            TrackerFingerprintSample.query
            .filter(TrackerFingerprintSample.device_id == dev.public_id)
            .filter(TrackerFingerprintSample.lat.isnot(None))
            .filter(TrackerFingerprintSample.lon.isnot(None))
            .filter(TrackerFingerprintSample.wifi_json.isnot(None))
            .filter(TrackerFingerprintSample.ts >= cutoff)
            .order_by(TrackerFingerprintSample.ts.desc())
            .limit(300)
            .all()
        )
        if not anchors:
            return None

        scored: List[Tuple[float, Dict[str, Any], TrackerFingerprintSample]] = []
        considered = 0
        for a in anchors:
            considered += 1
            # anchor quality filters
            try:
                am = a.meta() or {}
                if str(am.get("purpose") or "").lower() not in ("train", ""):
                    continue
                # optional GNSS freshness from client
                ga = am.get("gps_age_sec")
                if ga is not None:
                    try:
                        if int(ga) > 60:
                            continue
                    except Exception:
                        pass
            except Exception:
                am = {}

            try:
                if a.accuracy_m is not None and float(a.accuracy_m) > max_anchor_acc:
                    continue
            except Exception:
                pass

            aw = _wifi_vec(a.wifi(), k=10)
            if len(aw) < 3:
                continue
            ac = _cell_vec(a.cell(), k=6)
            score, det = _fp_similarity(w, aw, c, ac)
            if score <= 0:
                continue
            # minimal wifi match to avoid random estimates
            try:
                if int(det.get('matches_wifi') or 0) < min_wifi_matches:
                    continue
            except Exception:
                continue
            scored.append((score, det, a))

        if not scored:
            return None

        scored.sort(key=lambda x: x[0], reverse=True)

        # Build clusters (grid ~ 10-15m); each cluster keeps the best score
        clusters: Dict[Tuple[int, int], Dict[str, Any]] = {}
        for score, det, r in scored[:120]:
            try:
                lat0 = float(r.lat or 0.0)
                lon0 = float(r.lon or 0.0)
            except Exception:
                continue
            # approx 1e-4 deg ~ 11m in latitude
            key = (int(round(lat0 * 1e4)), int(round(lon0 * 1e4)))
            cobj = clusters.get(key)
            wgt = float(max(0.01, score)) ** 2
            if not cobj:
                clusters[key] = {
                    "sum_w": wgt,
                    "sum_lat": wgt * lat0,
                    "sum_lon": wgt * lon0,
                    "best_score": score,
                    "best_det": det,
                    "best_row": r,
                }
            else:
                cobj["sum_w"] += wgt
                cobj["sum_lat"] += wgt * lat0
                cobj["sum_lon"] += wgt * lon0
                if score > float(cobj.get("best_score") or 0.0):
                    cobj["best_score"] = score
                    cobj["best_det"] = det
                    cobj["best_row"] = r

        if not clusters:
            return None

        clist: List[Dict[str, Any]] = []
        for cobj in clusters.values():
            sw = float(cobj.get("sum_w") or 0.0)
            if sw <= 0:
                continue
            cobj["lat"] = float(cobj.get("sum_lat") or 0.0) / sw
            cobj["lon"] = float(cobj.get("sum_lon") or 0.0) / sw
            clist.append(cobj)

        clist.sort(key=lambda x: float(x.get("best_score") or 0.0), reverse=True)
        topc = clist[:3]
        best = topc[0]
        best_score = float(best.get("best_score") or 0.0)
        best_det = best.get("best_det") or {}
        best_row = best.get("best_row")

        best_matches_wifi = int(best_det.get("matches_wifi") or 0)
        best_matches_cell = int(best_det.get("matches_cell") or 0)

        # minimal accept rule
        if best_matches_wifi < min_wifi_matches or best_score < min_score:
            return None

        # weighted mean of cluster centers
        wsum = 0.0
        lat = 0.0
        lon = 0.0
        for cobj in topc:
            s0 = float(cobj.get("best_score") or 0.0)
            ww = float(max(0.01, s0)) ** 2
            wsum += ww
            lat += ww * float(cobj.get("lat") or 0.0)
            lon += ww * float(cobj.get("lon") or 0.0)
        if wsum <= 0:
            return None
        lat = lat / wsum
        lon = lon / wsum

        # spread (uncertainty) across top clusters
        spread_m = 0.0
        try:
            d2 = 0.0
            n = 0
            for cobj in topc:
                d = _haversine_m(lat, lon, float(cobj.get("lat") or 0.0), float(cobj.get("lon") or 0.0))
                d2 += d * d
                n += 1
            if n > 0:
                spread_m = math.sqrt(d2 / float(n))
        except Exception:
            spread_m = 0.0

        # base accuracy from best anchor + confidence + spread
        base_acc = None
        try:
            if best_row is not None and getattr(best_row, "accuracy_m", None) is not None:
                base_acc = float(best_row.accuracy_m)
        except Exception:
            base_acc = None
        if base_acc is None:
            base_acc = 50.0

        est_acc = base_acc * (1.0 + (1.0 - best_score) * 2.0) + spread_m
        est_acc = float(min(max(est_acc, 25.0), 260.0))

        # Diagnostics snapshot for UI
        rssi_diff_avg = best_det.get("rssi_diff_avg_db")
        try:
            rssi_diff_avg = float(rssi_diff_avg) if rssi_diff_avg is not None else None
        except Exception:
            rssi_diff_avg = None

        return {
            "lat": lat,
            "lon": lon,
            "accuracy_m": est_acc,
            "confidence": float(best_score),
            "matches": int(best_matches_wifi),  # backward-compat
            "matches_wifi": int(best_matches_wifi),
            "matches_cell": int(best_matches_cell),
            "rssi_diff_avg_db": rssi_diff_avg,
            "spread_m": float(spread_m),
            "anchor_ts": (best_row.ts.isoformat() if getattr(best_row, "ts", None) else None) if best_row is not None else None,
            "anchors_considered": int(len(scored)),
            "clusters_total": int(len(clusters)),
            "clusters_used": int(len(topc)),
        }
    except Exception:
        return None



def _inject_estimated_point(dev: TrackerDevice, est: Dict[str, Any]) -> bool:
    """Create and broadcast an estimated point (source=wifi_est) for active app session."""
    try:
        sess = TrackingSession.query.filter_by(user_id=dev.user_id, message_id=None, ended_at=None).order_by(TrackingSession.started_at.desc()).first()
        if not sess:
            return False

        # tuning knobs (env/config)
        try:
            throttle_sec = float(current_app.config.get('MAX_EST_THROTTLE_SEC', 30))
        except Exception:
            throttle_sec = 30.0

        # throttle: do not spam (>= 30 sec)
        try:
            last = TrackingPoint.query.filter_by(session_id=sess.id, kind='est').order_by(TrackingPoint.ts.desc()).first()
            if last and last.ts and (_utcnow() - last.ts).total_seconds() < throttle_sec:
                return False
        except Exception:
            pass

        ts = _utcnow()
        lat = float(est.get('lat'))
        lon = float(est.get('lon'))
        acc = est.get('accuracy_m')
        try:
            acc = float(acc) if acc is not None else None
        except Exception:
            acc = None

        tp = TrackingPoint(
            user_id=dev.user_id,
            session_id=sess.id,
            ts=ts,
            lat=lat,
            lon=lon,
            kind='est',
            accuracy_m=acc,
            raw_json=json.dumps(
                {
                    'src': 'wifi_est',
                    'method': est.get('method'),
                    'tile_id': est.get('tile_id'),
                    'tiles_considered': est.get('tiles_considered'),
                    'cell_diff_avg_db': est.get('cell_diff_avg_db'),
                    'confidence': est.get('confidence'),
                    'matches': est.get('matches'),
                    'matches_wifi': est.get('matches_wifi'),
                    'matches_cell': est.get('matches_cell'),
                    'rssi_diff_avg_db': est.get('rssi_diff_avg_db'),
                    'spread_m': est.get('spread_m'),
                    'anchor_ts': est.get('anchor_ts'),
                    'anchors_considered': est.get('anchors_considered'),
                    'clusters_total': est.get('clusters_total'),
                    'clusters_used': est.get('clusters_used'),
                },
                ensure_ascii=False,
            ),
        )
        db.session.add(tp)

        # update session last (so UI "Показать" works)
        sess.last_lat = lat
        sess.last_lon = lon
        sess.last_at = ts
        sess.is_active = True

        # also attach to health.extra_json (no schema migrations)
        try:
            h = TrackerDeviceHealth.query.filter_by(device_id=dev.public_id).first()
            if h:
                ex = h.extra() or {}
                ex['pos_est'] = {
                    'lat': lat,
                    'lon': lon,
                    'accuracy_m': acc,
                    'confidence': est.get('confidence'),
                    'matches': est.get('matches'),
                    'matches_wifi': est.get('matches_wifi'),
                    'matches_cell': est.get('matches_cell'),
                    'rssi_diff_avg_db': est.get('rssi_diff_avg_db'),
                    'spread_m': est.get('spread_m'),
                    'anchor_ts': est.get('anchor_ts'),
                    'anchors_considered': est.get('anchors_considered'),
                    'clusters_total': est.get('clusters_total'),
                    'clusters_used': est.get('clusters_used'),
                    'ts': ts.isoformat(),
                    'src': 'wifi_est',
                    'method': est.get('method'),
                    'tile_id': est.get('tile_id'),
                    'tiles_considered': est.get('tiles_considered'),
                    'cell_diff_avg_db': est.get('cell_diff_avg_db'),
                }
                h.extra_json = json.dumps(ex, ensure_ascii=False)
        except Exception:
            pass

        db.session.commit()

        broadcast_event_sync(
            'tracking_point',
            {
                'device_id': dev.public_id,
                'user_id': dev.user_id,
                'shift_id': sess.shift_id,
                'session_id': sess.id,
                'lat': lat,
                'lon': lon,
                'ts': ts.isoformat(),
                'accuracy_m': acc,
                'speed_mps': None,
                'bearing_deg': None,
                'flags': ['est'],
                'source': 'wifi_est',
                'method': est.get('method'),
                'tile_id': est.get('tile_id'),
                'tiles_considered': est.get('tiles_considered'),
                'cell_diff_avg_db': est.get('cell_diff_avg_db'),
                'confidence': est.get('confidence'),
                'matches': est.get('matches'),
                'matches_wifi': est.get('matches_wifi'),
                'matches_cell': est.get('matches_cell'),
                'rssi_diff_avg_db': est.get('rssi_diff_avg_db'),
                'spread_m': est.get('spread_m'),
                'anchor_ts': est.get('anchor_ts'),
                'anchors_considered': est.get('anchors_considered'),
                'clusters_total': est.get('clusters_total'),
                'clusters_used': est.get('clusters_used'),
            },
        )
        return True
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass
        return False






@bp.get("/api/tracker/admin/radio_map/stats")
def api_admin_radio_map_stats():
    """Статистика радио‑карты (tiles/AP/cell)."""
    require_admin("viewer")
    try:
        tiles = TrackerRadioTile.query.count()
    except Exception:
        tiles = 0
    try:
        aps = TrackerRadioAPStat.query.count()
    except Exception:
        aps = 0
    try:
        cells = TrackerRadioCellStat.query.count()
    except Exception:
        cells = 0
    try:
        latest = db.session.query(func.max(TrackerRadioTile.updated_at)).scalar()
    except Exception:
        latest = None
    return jsonify({
        "tiles": int(tiles or 0),
        "aps": int(aps or 0),
        "cells": int(cells or 0),
        "updated_at": latest.isoformat() if latest else None,
    })


# -------------------------
# MAX Indoor: radio-map tiles (общая радио-карта)
# -------------------------

def _tile_id_for_latlon(lat: float, lon: float, scale: int = 1000) -> str:
    """Grid tile id.

    scale=1000 => ~111m по широте.
    """
    try:
        return f"{int(round(float(lat) * scale))}_{int(round(float(lon) * scale))}"
    except Exception:
        return "0_0"


def _welford_push(mean: Optional[float], m2: Optional[float], count: int, x: float) -> tuple[float, float, int]:
    """Welford online update for mean/variance."""
    c0 = int(count or 0)
    c1 = c0 + 1
    if mean is None or not isinstance(mean, (int, float)):
        return float(x), 0.0, c1
    mu = float(mean)
    m2v = float(m2 or 0.0)
    delta = float(x) - mu
    mu2 = mu + delta / c1
    m2v2 = m2v + delta * (float(x) - mu2)
    return mu2, m2v2, c1


def _radio_train_update(lat: float, lon: float, wifi: list[dict], cell: list[dict]) -> None:
    """Update aggregated radio-map tile stats.

    Called only for samples with reliable GNSS.
    Best-effort: never breaks tracking.
    """
    try:
        tile_id = _tile_id_for_latlon(lat, lon, 1000)
        tile = TrackerRadioTile.query.get(tile_id)
        if not tile:
            tile = TrackerRadioTile(
                tile_id=tile_id,
                center_lat=float(lat),
                center_lon=float(lon),
                samples_count=0,
                ap_count=0,
                cell_count=0,
                updated_at=_utcnow(),
            )
            db.session.add(tile)

        # update tile center with incremental average
        try:
            n = int(tile.samples_count or 0)
            n2 = n + 1
            tile.center_lat = (float(tile.center_lat) * n + float(lat)) / n2
            tile.center_lon = (float(tile.center_lon) * n + float(lon)) / n2
            tile.samples_count = n2
            tile.updated_at = _utcnow()
        except Exception:
            pass

        # Wi‑Fi stats: keep top ~20 strongest
        wifi_items = list(wifi or [])
        wifi_items = [x for x in wifi_items if isinstance(x, dict) and x.get('bssid_hash') and x.get('rssi') is not None]
        wifi_items.sort(key=lambda x: float(x.get('rssi') or -999), reverse=True)
        wifi_items = wifi_items[:20]

        created_ap = 0
        for it in wifi_items:
            bh = str(it.get('bssid_hash') or '')
            try:
                rssi = float(it.get('rssi'))
            except Exception:
                continue
            row = TrackerRadioAPStat.query.filter_by(tile_id=tile_id, bssid_hash=bh).first()
            if not row:
                row = TrackerRadioAPStat(tile_id=tile_id, bssid_hash=bh, count=0, rssi_mean=None, rssi_m2=None, updated_at=_utcnow())
                db.session.add(row)
                created_ap += 1
            mu, m2, c = _welford_push(row.rssi_mean, row.rssi_m2, int(row.count or 0), rssi)
            row.rssi_mean = mu
            row.rssi_m2 = m2
            row.count = c
            row.updated_at = _utcnow()

        # Cell stats: keep up to ~8
        cell_items = list(cell or [])
        cell_items = [x for x in cell_items if isinstance(x, dict) and x.get('key_hash') and x.get('dbm') is not None]
        cell_items = cell_items[:8]

        created_cell = 0
        for it in cell_items:
            kh = str(it.get('key_hash') or '')
            try:
                dbm = float(it.get('dbm'))
            except Exception:
                continue
            row = TrackerRadioCellStat.query.filter_by(tile_id=tile_id, cell_key_hash=kh).first()
            if not row:
                row = TrackerRadioCellStat(tile_id=tile_id, cell_key_hash=kh, count=0, dbm_mean=None, dbm_m2=None, updated_at=_utcnow())
                db.session.add(row)
                created_cell += 1
            mu, m2, c = _welford_push(row.dbm_mean, row.dbm_m2, int(row.count or 0), dbm)
            row.dbm_mean = mu
            row.dbm_m2 = m2
            row.count = c
            row.updated_at = _utcnow()

        # update counts approximately (no heavy COUNT(*))
        try:
            if created_ap:
                tile.ap_count = int(tile.ap_count or 0) + created_ap
            if created_cell:
                tile.cell_count = int(tile.cell_count or 0) + created_cell
        except Exception:
            pass

    except Exception:
        # best-effort; no rollback here to avoid breaking main transaction
        pass


def _radio_candidate_tiles(wifi_keys: list[str], cell_keys: list[str], limit: int = 120) -> list[tuple[str, int]]:
    """Return candidate tiles with rough match count."""
    tiles: dict[str, int] = {}
    try:
        if wifi_keys:
            rows = (
                db.session.query(TrackerRadioAPStat.tile_id, func.count(TrackerRadioAPStat.id))
                .filter(TrackerRadioAPStat.bssid_hash.in_(wifi_keys))
                .group_by(TrackerRadioAPStat.tile_id)
                .order_by(func.count(TrackerRadioAPStat.id).desc())
                .limit(limit)
                .all()
            )
            for tid, c in rows:
                tiles[str(tid)] = tiles.get(str(tid), 0) + int(c or 0)
        if cell_keys:
            rows = (
                db.session.query(TrackerRadioCellStat.tile_id, func.count(TrackerRadioCellStat.id))
                .filter(TrackerRadioCellStat.cell_key_hash.in_(cell_keys))
                .group_by(TrackerRadioCellStat.tile_id)
                .order_by(func.count(TrackerRadioCellStat.id).desc())
                .limit(limit)
                .all()
            )
            for tid, c in rows:
                tiles[str(tid)] = tiles.get(str(tid), 0) + int(c or 0)
    except Exception:
        pass

    out = sorted(tiles.items(), key=lambda kv: kv[1], reverse=True)
    return out[:limit]


def _radio_score_tile(tile_id: str, wifi_vec: dict[str, float], cell_vec: dict[str, float]) -> dict[str, Any]:
    """Compute similarity score between current fingerprint and a tile."""
    # Load stats only for keys we have to keep query small
    wifi_keys = list(wifi_vec.keys())
    cell_keys = list(cell_vec.keys())

    ap_rows: list[TrackerRadioAPStat] = []
    cell_rows: list[TrackerRadioCellStat] = []
    try:
        if wifi_keys:
            ap_rows = TrackerRadioAPStat.query.filter(TrackerRadioAPStat.tile_id == tile_id, TrackerRadioAPStat.bssid_hash.in_(wifi_keys)).all()
        if cell_keys:
            cell_rows = TrackerRadioCellStat.query.filter(TrackerRadioCellStat.tile_id == tile_id, TrackerRadioCellStat.cell_key_hash.in_(cell_keys)).all()
    except Exception:
        ap_rows = []
        cell_rows = []

    # Wi‑Fi rssi similarity
    rssi_diffs: list[float] = []
    wifi_matches = 0
    for r in ap_rows:
        k = str(r.bssid_hash)
        if k in wifi_vec and r.rssi_mean is not None:
            wifi_matches += 1
            rssi_diffs.append(abs(float(wifi_vec[k]) - float(r.rssi_mean)))

    # Cell similarity
    cell_diffs: list[float] = []
    cell_matches = 0
    for r in cell_rows:
        k = str(r.cell_key_hash)
        if k in cell_vec and r.dbm_mean is not None:
            cell_matches += 1
            cell_diffs.append(abs(float(cell_vec[k]) - float(r.dbm_mean)))

    # combine
    rssi_avg = (sum(rssi_diffs)/len(rssi_diffs)) if rssi_diffs else None
    cell_avg = (sum(cell_diffs)/len(cell_diffs)) if cell_diffs else None

    # normalized component scores
    wifi_overlap = 0.0
    if wifi_vec:
        wifi_overlap = wifi_matches / max(1.0, float(min(len(wifi_vec), 12)))
    cell_overlap = 0.0
    if cell_vec:
        cell_overlap = cell_matches / max(1.0, float(min(len(cell_vec), 4)))

    # rssi closeness: 0..1 (10dB -> ~1, 40dB -> ~0)
    wifi_closeness = 0.0
    if rssi_avg is not None:
        wifi_closeness = max(0.0, 1.0 - float(rssi_avg) / 35.0)

    cell_closeness = 0.0
    if cell_avg is not None:
        cell_closeness = max(0.0, 1.0 - float(cell_avg) / 25.0)

    # final score (Wi‑Fi dominant)
    score = 0.0
    score += 0.65 * (0.55 * wifi_overlap + 0.45 * wifi_closeness)
    score += 0.25 * (0.55 * cell_overlap + 0.45 * cell_closeness)

    # small bonus for both channels present
    if wifi_matches >= 4 and cell_matches >= 1:
        score += 0.05

    score = max(0.0, min(1.0, score))

    return {
        'tile_id': tile_id,
        'score': score,
        'matches_wifi': wifi_matches,
        'matches_cell': cell_matches,
        'rssi_diff_avg_db': rssi_avg,
        'cell_diff_avg_db': cell_avg,
    }


def _localize_by_radio_map(wifi: list[dict], cell: list[dict]) -> Optional[Dict[str, Any]]:
    """Estimate position using aggregated radio-map tiles."""
    try:
        # tuning knobs (env/config)
        try:
            min_score = float(current_app.config.get('RADIO_MIN_SCORE', 0.45))
        except Exception:
            min_score = 0.45
        try:
            min_wifi_matches = int(current_app.config.get('RADIO_MIN_WIFI_MATCHES', 3))
        except Exception:
            min_wifi_matches = 3
        try:
            min_cell_matches = int(current_app.config.get('RADIO_MIN_CELL_MATCHES', 2))
        except Exception:
            min_cell_matches = 2

        # Build vectors from current sample
        wifi_vec: dict[str, float] = {}
        for it in (wifi or [])[:20]:
            if not isinstance(it, dict):
                continue
            k = it.get('bssid_hash')
            if not k:
                continue
            try:
                wifi_vec[str(k)] = float(it.get('rssi'))
            except Exception:
                pass

        cell_vec: dict[str, float] = {}
        for it in (cell or [])[:8]:
            if not isinstance(it, dict):
                continue
            k = it.get('key_hash')
            if not k:
                continue
            try:
                cell_vec[str(k)] = float(it.get('dbm'))
            except Exception:
                pass

        if len(wifi_vec) < 3 and len(cell_vec) < 2:
            return None

        cand = _radio_candidate_tiles(list(wifi_vec.keys()), list(cell_vec.keys()), limit=120)
        if not cand:
            return None

        # score top K candidates
        scored: list[dict] = []
        for tid, _c in cand[:80]:
            try:
                scored.append(_radio_score_tile(str(tid), wifi_vec, cell_vec))
            except Exception:
                continue

        if not scored:
            return None
        scored.sort(key=lambda x: float(x.get('score') or 0.0), reverse=True)
        best = scored[0]

        # require minimum signal
        if float(best.get('score') or 0.0) < 0.45:
            return None
        if int(best.get('matches_wifi') or 0) < 3 and int(best.get('matches_cell') or 0) < 2:
            return None

        tile = TrackerRadioTile.query.get(str(best.get('tile_id')))
        if not tile:
            return None

        # convert score to a more conservative confidence
        conf = float(best.get('score') or 0.0)
        conf = max(0.0, min(1.0, conf))

        # accuracy estimate (~20..160m)
        acc_m = 160.0 - conf * 120.0
        acc_m = max(20.0, min(160.0, acc_m))

        return {
            'lat': float(tile.center_lat),
            'lon': float(tile.center_lon),
            'accuracy_m': acc_m,
            'confidence': conf,
            'matches_wifi': int(best.get('matches_wifi') or 0),
            'matches_cell': int(best.get('matches_cell') or 0),
            'rssi_diff_avg_db': best.get('rssi_diff_avg_db'),
            'cell_diff_avg_db': best.get('cell_diff_avg_db'),
            'tile_id': str(tile.tile_id),
            'tiles_considered': min(len(cand), 80),
            'method': 'radio_tile',
            'source': 'wifi_cell_tile',
        }
    except Exception:
        return None


@bp.post("/api/tracker/fingerprints")
def api_fingerprints():
    """Радио-отпечаток Wi‑Fi + Cell от приложения.

    Это *не* замена GPS-точек. Это отдельный канал данных, который позволяет:
      - обучать радио-карту мест (когда координата надёжна)
      - в будущем оценивать позицию в здании/при плохом GPS (по похожести отпечатков)

    Тело (batched):
      {"samples": [
        {"ts": "2026-01-05T10:00:00Z", "lat": 52.5, "lon": 13.4, "accuracy_m": 9.2,
         "wifi": [{"bssid": "aa:bb:cc:dd:ee:ff", "ssid": "Home", "rssi": -55, "freq": 2412}],
         "cell": [{"type": "lte", "mcc": 262, "mnc": 1, "ci": 123, "tac": 456, "pci": 78}],
         "mode": "AUTO", "purpose": "train"}
      ]}

    Privacy: сервер **хэширует** BSSID/SSID и хранит только хэши + уровни сигнала.
    """
    dev, err = _require_device()
    if err:
        return err

    rl = _rl_fp(dev)
    if rl:
        return rl

    data = request.get_json(silent=True) or {}
    samples = data.get("samples")

    # allow sending a single sample directly (without wrapping)
    if samples is None and isinstance(data, dict) and any(k in data for k in ("wifi", "cell", "ts", "lat", "lon")):
        samples = [data]

    if isinstance(samples, dict):
        samples = [samples]

    if not isinstance(samples, list):
        return _err("bad_request", "samples must be a list", 400)

    # hard limits to protect DB
    samples = samples[:50]

    def _float(v):
        try:
            return float(v) if v is not None else None
        except Exception:
            return None

    def _dt(v):
        if not v:
            return None
        try:
            if isinstance(v, (int, float)):
                f = float(v)
                return datetime.utcfromtimestamp(f/1000.0 if f > 10_000_000_000 else f)
            return datetime.fromisoformat(str(v).replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            return None

    def _is_sha256_hex(s: str) -> bool:
        return bool(re.fullmatch(r"[0-9a-fA-F]{64}", s or ""))

    def _hash(v: str) -> str:
        return _sha256_hex((v or "").strip().lower())

    def _sanitize_wifi(items: Any) -> list[dict]:
        if not isinstance(items, list):
            return []
        out: list[dict] = []
        for it in items[:32]:
            if not isinstance(it, dict):
                continue
            bssid = (it.get("bssid") or it.get("bssid_hash") or "").strip()
            ssid = (it.get("ssid") or it.get("ssid_hash") or "").strip()
            bh = bssid if _is_sha256_hex(bssid) else (_hash(bssid) if bssid else None)
            sh = ssid if _is_sha256_hex(ssid) else (_hash(ssid) if ssid else None)
            rssi = _float(it.get("rssi"))
            freq = _float(it.get("freq"))
            rec = {}
            if bh: rec["bssid_hash"] = bh
            if sh: rec["ssid_hash"] = sh
            if rssi is not None: rec["rssi"] = rssi
            if freq is not None: rec["freq"] = freq
            if rec:
                out.append(rec)
        return out

    def _sanitize_cell(items: Any) -> list[dict]:
        if not isinstance(items, list):
            return []
        out: list[dict] = []
        for it in items[:16]:
            if not isinstance(it, dict):
                continue
            rec = {}
            for k in ("type", "mcc", "mnc", "ci", "tac", "lac", "psc", "pci", "sid", "nid", "bid", "dbm", "asu"):
                v = it.get(k)
                if v is None:
                    continue
                # keep numeric values numeric when possible
                if k == "type":
                    rec[k] = str(v)[:16]
                else:
                    try:
                        rec[k] = int(v)
                    except Exception:
                        try:
                            rec[k] = float(v)
                        except Exception:
                            pass
            if rec:
                out.append(rec)
        return out

    stored = 0
    dropped = 0
    now = _utcnow()

    # last sample snapshot (for optional indoor localization)
    last_wifi: List[Dict[str, Any]] = []
    last_cell: List[Dict[str, Any]] = []
    last_lat: Optional[float] = None
    last_lon: Optional[float] = None
    last_acc: Optional[float] = None
    last_meta: Dict[str, Any] = {}

    for s in samples:
        if not isinstance(s, dict):
            dropped += 1
            continue

        ts = _dt(s.get("ts")) or now
        lat = _float(s.get("lat"))
        lon = _float(s.get("lon"))
        acc = _float(s.get("accuracy_m") or s.get("acc"))

        wifi = _sanitize_wifi(s.get("wifi"))
        cell = _sanitize_cell(s.get("cell"))

        meta = {}
        # short string tags
        for k in ("mode", "purpose", "source", "note"):
            v = s.get(k)
            if v is not None:
                meta[k] = str(v)[:64]

        # diagnostics / quality (keep as numeric where possible)
        try:
            ga = s.get("gps_age_sec")
            if ga is not None:
                meta["gps_age_sec"] = int(ga)
        except Exception:
            pass
        try:
            la = s.get("gps_last_accepted")
            if la is not None:
                meta["gps_last_accepted"] = str(la)[:64]
        except Exception:
            pass
        try:
            fr = s.get("filter_rejects")
            if fr is not None:
                meta["filter_rejects"] = int(fr)
        except Exception:
            pass
        try:
            lf = s.get("last_filter")
            if lf is not None:
                meta["last_filter"] = str(lf)[:128]
        except Exception:
            pass

        # MAX Indoor: обучаем radio-map плитки только при надёжном GNSS
        try:
            purpose_tag = str(meta.get('purpose') or '').strip().lower()
            gps_age = meta.get('gps_age_sec') if isinstance(meta.get('gps_age_sec'), int) else None
            good_acc = (acc is not None) and (acc > 0) and (acc <= 60)
            good_gps = (lat is not None and lon is not None and good_acc and (gps_age is None or gps_age <= 45))
            if good_gps and purpose_tag != 'locate':
                _radio_train_update(lat, lon, wifi, cell)
        except Exception:
            pass

        # remember the last sanitized sample
        last_wifi = wifi
        last_cell = cell
        last_lat = lat
        last_lon = lon
        last_acc = acc
        last_meta = meta

        row = TrackerFingerprintSample(
            device_id=dev.public_id,
            user_id=dev.user_id,
            ts=ts,
            lat=lat,
            lon=lon,
            accuracy_m=acc,
            wifi_json=json.dumps(wifi, ensure_ascii=False) if wifi else None,
            cell_json=json.dumps(cell, ensure_ascii=False) if cell else None,
            meta_json=json.dumps(meta, ensure_ascii=False) if meta else None,
            created_at=_utcnow(),
        )
        db.session.add(row)
        stored += 1

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return _err("db_error", "Failed to store fingerprints", 500)

    # Optional: if this sample is meant for "locate" (no reliable GNSS),
    # try to estimate position by similarity to previously trained anchors.
    pos_est: Optional[Dict[str, Any]] = None
    localized = False
    try:
        purpose = str((last_meta or {}).get('purpose') or '').strip().lower()
        need_loc = (purpose == 'locate') or (last_lat is None or last_lon is None) or (last_acc is not None and last_acc > 80)
        if need_loc and ((last_wifi and len(last_wifi) >= 3) or (last_cell and len(last_cell) >= 2)):
            # 1) глобальная radio-map (плитки) — хорошо для indoor и для новой установки
            pos_est = _localize_by_radio_map(last_wifi, last_cell)

            # 2) fallback: якоря по конкретному устройству (если Wi‑Fi достаточно)
            if not pos_est and last_wifi and len(last_wifi) >= 3:
                pos_est = _localize_by_fingerprint(dev, last_wifi, last_cell)

            if pos_est:
                localized = _inject_estimated_point(dev, pos_est)
    except Exception:
        pos_est = None
        localized = False
    try:
        broadcast_event_sync("tracker_fingerprint", {
            "device_id": dev.public_id,
            "user_id": dev.user_id,
            "stored": stored,
        })
    except Exception:
        pass

    resp: Dict[str, Any] = {"stored": stored, "dropped": dropped}
    if pos_est:
        resp["pos_est"] = pos_est
        resp["localized"] = bool(localized)
    return _ok(resp)


# -------------------------
# Mobile bootstrap (Telegram -> Android)
# -------------------------

def _require_bootstrap_access() -> None:
    """Проверить BOT_API_KEY и allow-list Telegram user_id (опционально)."""
    require_bot_api_key(allow_query_param=True)
    allow_ids = current_app.config.get("BOOTSTRAP_ALLOWED_TELEGRAM_IDS") or current_app.config.get("ADMIN_TELEGRAM_IDS") or set()
    if allow_ids:
        tg_id = (request.headers.get("X-Telegram-Id") or request.args.get("tg_id") or "").strip()
        if (not tg_id.isdigit()) or (int(tg_id) not in allow_ids):
            abort(403)


@bp.post("/api/mobile/bootstrap/request")
def api_mobile_bootstrap_request():
    """Запросить одноразовый bootstrap-токен + pairing-code для Android.

    Используется Telegram-ботом:
      - BOT_API_KEY обязателен, если задан в конфиге
      - X-Telegram-Id (или tg_id) проверяется через allow-list при необходимости
    """
    _require_bootstrap_access()
    data = request.get_json(silent=True) or {}

    base_url = (data.get("base_url") or "").strip() or None
    # "auto" — это UI-заглушка
    if base_url and base_url.lower() == "auto":
        base_url = None
    label = (data.get("label") or "").strip()[:128] or None
    tg_user_id = (data.get("tg_user_id") or request.headers.get("X-Telegram-Id") or "").strip()[:64] or None

    ttl_min = int(current_app.config.get("BOOTSTRAP_TTL_MIN") or 10)

    # 1) pairing code (чтобы Android мог получить device_token стандартным /api/tracker/pair)
    code = f"{secrets.randbelow(1000000):06d}"
    code_hash = _sha256_hex(code)
    pc = TrackerPairCode(
        code_hash=code_hash,
        created_at=_utcnow(),
        expires_at=_utcnow() + timedelta(minutes=ttl_min),
        used_at=None,
        label=label,
    )
    db.session.add(pc)

    # 2) bootstrap token (для выдачи конфига через отдельный endpoint)
    token = secrets.token_urlsafe(24)
    token_hash = _sha256_hex(token)
    bt = TrackerBootstrapToken(
        token_hash=token_hash,
        pair_code=code,
        created_at=_utcnow(),
        expires_at=_utcnow() + timedelta(minutes=ttl_min),
        used_at=None,
        tg_user_id=tg_user_id,
        label=label,
        base_url=base_url,
    )
    db.session.add(bt)
    db.session.commit()

    return _ok({
        "token": token,
        "expires_in_min": ttl_min,
        "base_url": base_url,
        "pair_code": code,
        "label": label,
    })


@bp.get("/api/mobile/bootstrap/config")
def api_mobile_bootstrap_config():
    """Выдать конфиг по одноразовому bootstrap-токену."""
    token = (request.args.get("token") or "").strip()
    if not token:
        return _err("token_required", "token is required", status=400)

    token_hash = _sha256_hex(token)
    row = TrackerBootstrapToken.query.filter_by(token_hash=token_hash).first()
    if not row:
        return _err("token_not_found", "token not found", status=404)

    now = _utcnow()
    if row.used_at is not None:
        return _err("token_used", "token already used", status=409)
    if row.expires_at and now >= row.expires_at:
        return _err("token_expired", "token expired", status=410)

    # одноразовый: фиксируем использование
    row.used_at = now
    db.session.commit()

    # base_url: приоритет у того, что передал бот; иначе — из запроса
    base_url = (row.base_url or "").strip() or request.url_root.rstrip("/")

    return _ok({
        "base_url": base_url,
        "pair_code": row.pair_code,
        "label": row.label,
        "tg_user_id": row.tg_user_id,
    })


# -------------------------
# Mobile connect (DutyTracker bootstrap flow with admin approve)
# -------------------------

CONNECT_STATUSES = {"pending", "approved", "denied"}


def _get_service_status(tg_user_id: str) -> str:
    tg_user_id = (tg_user_id or "").strip()
    if not tg_user_id:
        return "guest"
    row = ServiceAccess.query.filter_by(tg_user_id=str(tg_user_id)).first()
    if not row:
        return "guest"
    try:
        return row.normalize_status()
    except Exception:
        return (row.status or "guest").strip().lower() or "guest"


def _require_service_role(tg_user_id: str) -> None:
    s = _get_service_status(tg_user_id)
    if s not in {"officer", "admin"}:
        abort(403)


def _server_port_from_request(default_port: int = 5000) -> int:
    try:
        host = (request.host or "").strip()
        if ":" in host:
            return int(host.rsplit(":", 1)[-1])
    except Exception:
        pass
    try:
        return int(os.environ.get("PORT", str(default_port)))
    except Exception:
        return default_port


def _is_good_ipv4(ip: str) -> bool:
    ip = (ip or "").strip()
    if not ip:
        return False
    if ip.startswith("127.") or ip.startswith("0."):
        return False
    return True


def _guess_ipv4_addrs() -> List[str]:
    import socket

    ips = set()

    # 1) UDP trick: find primary outbound ip
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if _is_good_ipv4(ip):
            ips.add(ip)
    except Exception:
        pass

    # 2) hostname resolution
    try:
        host = socket.gethostname()
        for _family, _socktype, _proto, _canon, sockaddr in socket.getaddrinfo(host, None):
            try:
                ip = sockaddr[0]
                if _is_good_ipv4(ip):
                    ips.add(ip)
            except Exception:
                pass
    except Exception:
        pass

    out = list(ips)

    def _prio(x: str) -> int:
        # RFC1918 first
        if x.startswith("192.168."):
            return 0
        if x.startswith("10."):
            return 1
        if x.startswith("172."):
            try:
                p2 = int(x.split(".")[1])
                if 16 <= p2 <= 31:
                    return 2
            except Exception:
                pass
        # VPN-like ranges often 100.x.x.x (Tailscale/ZeroTier)
        if x.startswith("100."):
            return 3
        return 9

    out.sort(key=lambda x: (_prio(x), x))
    return out


def _normalize_base_url(base_url: Optional[str]) -> str:
    # explicit preferred base url
    preferred = (current_app.config.get("BOOTSTRAP_PREFERRED_BASE_URL") or "").strip()
    if preferred:
        return preferred.rstrip("/")

    raw = (base_url or "").strip()
    if raw and raw.lower() != "auto":
        return raw.rstrip("/")

    # If the request came through a reverse-proxy (Cloudflare Tunnel / HTTPS),
    # prefer the externally visible URL instead of guessing LAN IPs.
    try:
        root = (request.url_root or "").rstrip("/")
    except Exception:
        root = ""

    host = (request.host or "").lower().strip()
    if host.endswith("trycloudflare.com") and root.startswith("http://"):
        root = "https://" + root[len("http://"):]
    if root.startswith("https://") or host.endswith("trycloudflare.com") or host.endswith(".workers.dev"):
        return root or ""

    # Local dev / LAN fallback: guess a reachable RFC1918 address
    port = _server_port_from_request()
    ips = _guess_ipv4_addrs()
    if ips:
        return f"http://{ips[0]}:{port}"
    # fallback (can be 127.0.0.1)
    return root or request.url_root.rstrip("/")


def _issue_bootstrap_token(*, tg_user_id: str, base_url: Optional[str], label: Optional[str]) -> Dict[str, Any]:
    """Выпустить bootstrap token + pairing code (как /api/mobile/bootstrap/request)."""
    ttl_min = int(current_app.config.get("BOOTSTRAP_TTL_MIN") or 10)
    base_url_norm = _normalize_base_url(base_url)

    # pairing code row (для стандартного /api/tracker/pair)
    code = f"{secrets.randbelow(1000000):06d}"
    code_hash = _sha256_hex(code)
    pc = TrackerPairCode(
        code_hash=code_hash,
        created_at=_utcnow(),
        expires_at=_utcnow() + timedelta(minutes=ttl_min),
        used_at=None,
        label=(label or None),
    )
    db.session.add(pc)

    # bootstrap token row
    token = secrets.token_urlsafe(24)
    token_hash = _sha256_hex(token)
    bt = TrackerBootstrapToken(
        token_hash=token_hash,
        pair_code=code,
        created_at=_utcnow(),
        expires_at=_utcnow() + timedelta(minutes=ttl_min),
        used_at=None,
        base_url=base_url_norm,
        label=(label or None),
        tg_user_id=str(tg_user_id),
    )
    db.session.add(bt)
    db.session.commit()

    return {
        "token": token,
        "token_hash": token_hash,
        "pair_code": code,
        "expires_in_min": ttl_min,
        "base_url": base_url_norm,
    }


def _connect_request_view(row: TrackerConnectRequest) -> Dict[str, Any]:
    out = row.to_dict()
    token_state = None
    token_used_at = None
    token_expires_at = None

    if row.last_bootstrap_token_hash:
        bt = TrackerBootstrapToken.query.filter_by(token_hash=row.last_bootstrap_token_hash).first()
        if bt:
            token_used_at = bt.used_at.isoformat() + "Z" if bt.used_at else None
            token_expires_at = bt.expires_at.isoformat() + "Z" if bt.expires_at else None
            if bt.used_at:
                token_state = "used"
            elif bt.expires_at and _utcnow() >= bt.expires_at:
                token_state = "expired"
            else:
                token_state = "active"
        else:
            token_state = "missing"

    out["last_token_state"] = token_state
    out["last_token_used_at"] = token_used_at
    out["last_token_expires_at"] = token_expires_at
    out["service_status"] = _get_service_status(row.tg_user_id)
    return out


@bp.post("/api/mobile/connect/request")
def api_mobile_connect_request():
    """Создать/переоткрыть заявку на привязку DutyTracker.

    Auth: BOT_API_KEY (X-API-KEY). Требуется роль officer/admin (через ServiceAccess).
    """
    require_bot_api_key(allow_query_param=False)
    data = request.get_json(silent=True) or {}
    tg_user_id = (data.get("tg_user_id") or request.headers.get("X-Telegram-Id") or "").strip()[:64]
    if not tg_user_id:
        return _err("missing_tg_user_id", "tg_user_id is required", status=400)

    # only approved service members can request tracker connect
    _require_service_role(tg_user_id)

    note = (data.get("note") or "").strip()[:256] or None
    base_url = (data.get("base_url") or "").strip() or None

    row = TrackerConnectRequest.query.filter_by(tg_user_id=str(tg_user_id)).first()
    now = _utcnow()
    if not row:
        row = TrackerConnectRequest(
            tg_user_id=str(tg_user_id),
            status="pending",
            note=note,
            base_url=base_url,
            created_at=now,
            updated_at=now,
        )
        db.session.add(row)
    else:
        # reopen if denied
        if row.status == "denied":
            row.status = "pending"
            row.denied_at = None
        row.updated_at = now
        if note:
            row.note = note
        if base_url:
            row.base_url = base_url

    db.session.commit()
    return _ok({"status": row.status, "request": _connect_request_view(row)})


@bp.get("/api/mobile/connect/status")
def api_mobile_connect_status():
    """Статус заявки. Если issue=1 и статус approved — выдаёт новый bootstrap токен."""
    require_bot_api_key(allow_query_param=False)
    tg_user_id = (request.args.get("tg_user_id") or request.headers.get("X-Telegram-Id") or "").strip()[:64]
    if not tg_user_id:
        return _err("missing_tg_user_id", "tg_user_id is required", status=400)

    row = TrackerConnectRequest.query.filter_by(tg_user_id=str(tg_user_id)).first()
    if not row:
        return _ok({"status": "none"})

    # If user does not have service role anymore — hard stop
    _require_service_role(tg_user_id)

    issue = (request.args.get("issue") or "").strip() in {"1", "true", "yes"}

    if issue and row.status == "approved":
        label = (row.note or None)
        issued = _issue_bootstrap_token(tg_user_id=str(tg_user_id), base_url=row.base_url, label=label)
        row.last_bootstrap_token_hash = issued["token_hash"]
        row.last_pair_code = issued["pair_code"]
        row.last_issued_at = _utcnow()
        row.last_sent_via = "pull"
        row.last_send_error = None
        db.session.commit()
        view = _connect_request_view(row)
        view["issued"] = {
            "token": issued["token"],
            "pair_code": issued["pair_code"],
            "base_url": issued["base_url"],
            "expires_in_min": issued["expires_in_min"],
        }
        return _ok({"status": row.status, "request": view})

    return _ok({"status": row.status, "request": _connect_request_view(row)})


@bp.get("/api/mobile/connect/admin/pending")
def api_mobile_connect_admin_pending():
    require_admin("editor")
    q = TrackerConnectRequest.query.filter(TrackerConnectRequest.status == "pending").order_by(TrackerConnectRequest.created_at.asc())
    rows = q.limit(200).all()
    return jsonify([_connect_request_view(r) for r in rows]), 200


@bp.get("/api/mobile/connect/admin/pending_count")
def api_mobile_connect_admin_pending_count():
    """Кол-во pending заявок на подключение DutyTracker (для бейджа в Command Center)."""
    require_admin("editor")
    n = TrackerConnectRequest.query.filter(TrackerConnectRequest.status == "pending").count()
    return jsonify({"count": int(n)}), 200


@bp.post("/api/mobile/connect/admin/approve")
def api_mobile_connect_admin_approve():
    require_admin("editor")
    data = request.get_json(silent=True) or {}
    tg_user_id = (data.get("tg_user_id") or "").strip()[:64]
    if not tg_user_id:
        return jsonify({"error": "missing_tg_user_id"}), 400

    base_url = (data.get("base_url") or "").strip() or None
    # "auto" — это UI-заглушка
    if base_url and base_url.lower() == "auto":
        base_url = None
    note = (data.get("note") or "").strip()[:256] or None

    row = TrackerConnectRequest.query.filter_by(tg_user_id=str(tg_user_id)).first()
    now = _utcnow()
    if not row:
        row = TrackerConnectRequest(tg_user_id=str(tg_user_id), created_at=now, updated_at=now)
        db.session.add(row)

    row.status = "approved"
    row.approved_at = now
    row.denied_at = None
    row.updated_at = now
    if note:
        row.note = note
    # Если base_url не задан — используем auto-detect/BOOTSTRAP_PREFERRED_BASE_URL.
    # Если base_url передан — фиксируем его в заявке.
    if base_url is None:
        # очищаем, чтобы не «залип» устаревший LAN/127.0.0.1
        row.base_url = None
    else:
        row.base_url = base_url

    # issue token + auto send
    issued = _issue_bootstrap_token(tg_user_id=str(tg_user_id), base_url=row.base_url, label=row.note)
    row.last_bootstrap_token_hash = issued["token_hash"]
    row.last_pair_code = issued["pair_code"]
    row.last_issued_at = _utcnow()

    send_ok = False
    send_payload = None
    send_error = None

    bot_token = (current_app.config.get("TELEGRAM_BOT_TOKEN") or "").strip()
    auto_send = bool(current_app.config.get("MOBILE_CONNECT_AUTO_SEND", True))

    if bot_token and auto_send:
        try:
            send_payload = send_dutytracker_connect_button(
                bot_token,
                str(tg_user_id),
                issued["base_url"],
                issued["token"],
                issued["pair_code"],
            )
            send_ok = bool(send_payload.get("ok"))
            if not send_ok:
                send_error = str(send_payload)[:500]
        except Exception as e:
            send_error = f"{type(e).__name__}: {e}"

    if send_ok:
        row.last_sent_at = _utcnow()
        row.last_sent_via = "auto"
        row.last_send_error = None
    else:
        row.last_sent_via = "auto" if (bot_token and auto_send) else None
        row.last_send_error = (send_error or None)

    db.session.commit()

    # audit
    try:
        log_admin_action("mobile_connect.approve", {"tg_user_id": tg_user_id, "base_url": issued["base_url"], "send_ok": send_ok})
    except Exception:
        pass

    return jsonify({
        "ok": True,
        "status": row.status,
        "send_ok": send_ok,
        "send_payload": send_payload if (not send_ok and send_payload) else None,
        "send_error": send_error,
        "request": _connect_request_view(row),
    }), 200


@bp.post("/api/mobile/connect/admin/deny")
def api_mobile_connect_admin_deny():
    require_admin("editor")
    data = request.get_json(silent=True) or {}
    tg_user_id = (data.get("tg_user_id") or "").strip()[:64]
    if not tg_user_id:
        return jsonify({"error": "missing_tg_user_id"}), 400

    note = (data.get("note") or "").strip()[:256] or None

    row = TrackerConnectRequest.query.filter_by(tg_user_id=str(tg_user_id)).first()
    now = _utcnow()
    if not row:
        row = TrackerConnectRequest(tg_user_id=str(tg_user_id), created_at=now, updated_at=now)
        db.session.add(row)

    row.status = "denied"
    row.denied_at = now
    row.updated_at = now
    if note:
        row.note = note

    db.session.commit()
    try:
        log_admin_action("mobile_connect.deny", {"tg_user_id": tg_user_id})
    except Exception:
        pass

    return jsonify({"ok": True, "status": row.status, "request": _connect_request_view(row)}), 200


@bp.post("/api/mobile/connect/admin/reset")
def api_mobile_connect_admin_reset():
    require_admin("editor")
    data = request.get_json(silent=True) or {}
    tg_user_id = (data.get("tg_user_id") or "").strip()[:64]
    if not tg_user_id:
        return jsonify({"error": "missing_tg_user_id"}), 400

    row = TrackerConnectRequest.query.filter_by(tg_user_id=str(tg_user_id)).first()
    if not row:
        return jsonify({"ok": True, "status": "none"}), 200

    row.status = "pending"
    row.updated_at = _utcnow()
    row.denied_at = None
    db.session.commit()
    try:
        log_admin_action("mobile_connect.reset", {"tg_user_id": tg_user_id})
    except Exception:
        pass
    return jsonify({"ok": True, "status": row.status, "request": _connect_request_view(row)}), 200


# -------------------------
# Admin: generate pairing code
# -------------------------

@bp.post("/api/tracker/admin/pair-code")
def api_admin_pair_code():
    require_admin()
    data = request.get_json(silent=True) or {}
    label = (data.get("label") or "").strip()[:128] or None

    ttl_min = int(os.environ.get("TRACKER_PAIR_TTL_MIN", "10"))
    code = f"{secrets.randbelow(1000000):06d}"
    code_hash = _sha256_hex(code)

    pc = TrackerPairCode(
        code_hash=code_hash,
        created_at=_utcnow(),
        expires_at=_utcnow() + timedelta(minutes=ttl_min),
        used_at=None,
        label=label,
    )
    db.session.add(pc)
    db.session.commit()
    return _ok({'code': code, 'expires_in_min': ttl_min, 'label': label})


@bp.get("/api/tracker/admin/devices")
def api_admin_devices():
    """Список устройств для страницы /admin/devices.

    Возвращаем агрегат: устройство + профиль + health + флаги активной смены/трекинга.
    """
    require_admin("viewer")
    now = _utcnow()
    # pagination
    try:
        limit = int(request.args.get("limit", 200))
    except Exception:
        limit = 200
    try:
        offset = int(request.args.get("offset", 0))
    except Exception:
        offset = 0
    limit = max(20, min(limit, 2000))
    offset = max(0, offset)

    total = TrackerDevice.query.count()
    devs = (
        TrackerDevice.query
        .order_by(TrackerDevice.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    out: List[Dict[str, Any]] = []
    for d in devs:
        h = TrackerDeviceHealth.query.filter_by(device_id=d.public_id).first()
        health = h.to_dict() if h else None
        health_age_sec = None
        if h and h.updated_at:
            try:
                health_age_sec = int((now - h.updated_at).total_seconds())
            except Exception:
                health_age_sec = None

        sh = DutyShift.query.filter(DutyShift.user_id == d.user_id, DutyShift.ended_at == None).order_by(DutyShift.started_at.desc()).first()  # noqa: E711
        sess = TrackingSession.query.filter_by(user_id=d.user_id, ended_at=None).order_by(TrackingSession.started_at.desc()).first()

        # последняя точка (для быстрой диагностики)
        lp = TrackingPoint.query.filter(TrackingPoint.user_id == d.user_id).order_by(TrackingPoint.ts.desc()).first()
        last_point = None
        if lp and lp.ts is not None:
            last_point = {
                "lat": lp.lat,
                "lon": lp.lon,
                "ts": lp.ts.isoformat() if hasattr(lp.ts, "isoformat") else str(lp.ts),
                "kind": lp.kind,
            }

        out.append({
            "public_id": d.public_id,
            "label": d.label,
            "user_id": d.user_id,
            "created_at": d.created_at.isoformat() if d.created_at else None,
            "last_seen_at": d.last_seen_at.isoformat() if d.last_seen_at else None,
            "is_revoked": bool(d.is_revoked),
            "profile": d.profile(),
            "unit_label": sh.unit_label if sh else None,
            "active_shift_id": sh.id if sh else None,
            "tracking_active": bool(sess is not None),
            "last_point": last_point,
            "health": health,
            "health_age_sec": health_age_sec,
            "device_model": (h.device_model if h else None),
            "os_version": (h.os_version if h else None),
            "app_version": (h.app_version if h else None),
        })

    return jsonify({"server_time": now.isoformat(), "devices": out, "total": total, "limit": limit, "offset": offset, "has_more": (offset + limit) < total})


@bp.post("/api/tracker/admin/device/<string:device_id>/revoke")
def api_admin_device_revoke(device_id: str):
    """Отозвать устройство (запретить доступ токеном).

    Дополнительно: закрываем активную сессию трекинга, если она есть.
    """
    require_admin("superadmin")
    dev = TrackerDevice.query.filter_by(public_id=device_id).first()
    if not dev:
        return _err('bad_request', 'not found', 404)
    dev.is_revoked = True

    sess = TrackingSession.query.filter_by(user_id=dev.user_id, ended_at=None).order_by(TrackingSession.started_at.desc()).first()
    if sess:
        sess.ended_at = _utcnow()
        sess.is_active = False

    db.session.commit()
    _audit('REVOKE_DEVICE', device_id=dev.public_id, user_id=dev.user_id, payload={'ip': _client_ip()})
    broadcast_event_sync("tracker_device_updated", {"device_id": dev.public_id, "is_revoked": True})
    return _ok({})



@bp.post("/api/tracker/admin/device/<string:device_id>/rotate")
def api_admin_device_rotate(device_id: str):
    """Сменить токен устройства (rotation).

    Возвращает НОВЫЙ токен (показывать оператору/в приложении).
    Старый токен перестаёт работать сразу.
    """
    require_admin("superadmin")
    dev = TrackerDevice.query.filter_by(public_id=device_id).first()
    if not dev:
        return _err('bad_request', 'not found', 404)

    # генерим новый токен и обновляем hash
    token = secrets.token_hex(32)
    dev.token_hash = _sha256_hex(token)
    dev.is_revoked = False
    dev.last_seen_at = _utcnow()
    db.session.commit()

    _audit('ROTATE_DEVICE_TOKEN', device_id=dev.public_id, user_id=dev.user_id, payload={'ip': _client_ip()})
    broadcast_event_sync("tracker_device_updated", {"device_id": dev.public_id, "rotated": True, "is_revoked": False})
    return _ok({'device_id': dev.public_id, 'new_token': token})

@bp.post("/api/tracker/admin/device/<string:device_id>/restore")
def api_admin_device_restore(device_id: str):
    """Вернуть устройство (разрешить доступ токеном)."""
    require_admin("superadmin")
    dev = TrackerDevice.query.filter_by(public_id=device_id).first()
    if not dev:
        return _err('bad_request', 'not found', 404)
    dev.is_revoked = False
    db.session.commit()
    _audit('RESTORE_DEVICE', device_id=dev.public_id, user_id=dev.user_id, payload={'ip': _client_ip()})
    broadcast_event_sync("tracker_device_updated", {"device_id": dev.public_id, "is_revoked": False})
    return _ok({})


@bp.get("/api/tracker/admin/device/<string:device_id>")
def api_admin_device_detail(device_id: str):
    """Детальная информация по устройству (для /admin/devices/<id>)."""
    require_admin("viewer")
    now = _utcnow()
    dev = TrackerDevice.query.filter_by(public_id=device_id).first()
    if not dev:
        return _err('bad_request', 'not found', 404)

    h = TrackerDeviceHealth.query.filter_by(device_id=dev.public_id).first()
    sh = DutyShift.query.filter(DutyShift.user_id == dev.user_id, DutyShift.ended_at == None).order_by(DutyShift.started_at.desc()).first()  # noqa: E711
    sess = TrackingSession.query.filter_by(user_id=dev.user_id, ended_at=None).order_by(TrackingSession.started_at.desc()).first()

    lp = TrackingPoint.query.filter(TrackingPoint.user_id == dev.user_id).order_by(TrackingPoint.ts.desc()).first()
    last_point = None
    if lp and lp.ts is not None:
        last_point = {
            "lat": lp.lat,
            "lon": lp.lon,
            "ts": lp.ts.isoformat() if hasattr(lp.ts, "isoformat") else str(lp.ts),
            "kind": lp.kind,
            "session_id": lp.session_id,
            "accuracy_m": lp.accuracy_m,
        }

    health_age_sec = None
    if h and h.updated_at:
        try:
            health_age_sec = int((now - h.updated_at).total_seconds())
        except Exception:
            health_age_sec = None

    return jsonify({
        "server_time": now.isoformat(),
        "device": {
            "public_id": dev.public_id,
            "label": dev.label,
            "user_id": dev.user_id,
            "created_at": dev.created_at.isoformat() if dev.created_at else None,
            "last_seen_at": dev.last_seen_at.isoformat() if dev.last_seen_at else None,
            "is_revoked": bool(dev.is_revoked),
            "profile": dev.profile(),
            "active_shift_id": sh.id if sh else None,
            "unit_label": sh.unit_label if sh else None,
            "tracking_active": bool(sess is not None),
            "active_session_id": sess.id if sess else None,
            "health": h.to_dict() if h else None,
            "health_age_sec": health_age_sec,
            "last_point": last_point,
        }
    })


@bp.get("/api/tracker/admin/device/<string:device_id>/health_log")
def api_admin_device_health_log(device_id: str):
    """История health для графиков/таблиц.

    params:
      - limit (default 240)
      - hours (optional): если задано, отдаём только последние N часов
    """
    require_admin("viewer")
    dev = TrackerDevice.query.filter_by(public_id=device_id).first()
    if not dev:
        return _err('bad_request', 'not found', 404)

    try:
        limit = int(request.args.get("limit", 240))
    except Exception:
        limit = 240
    limit = max(10, min(limit, 2000))

    frm, to = _get_time_range_from_args()

    hours = request.args.get("hours")
    cutoff = None
    if (frm is None and to is None) and hours:
        try:
            cutoff = _utcnow() - timedelta(hours=float(hours))
        except Exception:
            cutoff = None

    q = TrackerDeviceHealthLog.query.filter_by(device_id=dev.public_id)
    # explicit range has priority
    if frm is not None:
        q = q.filter(TrackerDeviceHealthLog.ts >= frm)
    if to is not None:
        q = q.filter(TrackerDeviceHealthLog.ts <= to)
    elif cutoff is not None:
        q = q.filter(TrackerDeviceHealthLog.ts >= cutoff)

    rows = q.order_by(TrackerDeviceHealthLog.ts.desc()).limit(limit).all()
    return jsonify({
        "device_id": dev.public_id,
        "user_id": dev.user_id,
        "items": [r.to_dict() for r in rows],
    })


@bp.get("/api/tracker/admin/device/<string:device_id>/points")
def api_admin_device_points(device_id: str):
    """Последние точки трекинга по устройству (TrackingPoint)."""
    require_admin("viewer")
    dev = TrackerDevice.query.filter_by(public_id=device_id).first()
    if not dev:
        return _err('bad_request', 'not found', 404)

    try:
        limit = int(request.args.get("limit", 500))
    except Exception:
        limit = 500
    limit = max(20, min(limit, 5000))

    frm, to = _get_time_range_from_args()

    hours = request.args.get("hours")
    cutoff = None
    if (frm is None and to is None) and hours:
        try:
            cutoff = _utcnow() - timedelta(hours=float(hours))
        except Exception:
            cutoff = None

    q = TrackingPoint.query.filter(TrackingPoint.user_id == dev.user_id)
    if frm is not None:
        q = q.filter(TrackingPoint.ts >= frm)
    if to is not None:
        q = q.filter(TrackingPoint.ts <= to)
    elif cutoff is not None:
        q = q.filter(TrackingPoint.ts >= cutoff)

    pts = q.order_by(TrackingPoint.ts.desc()).limit(limit).all()
    out = []
    for p in pts:
        out.append({
            "id": p.id,
            "ts": p.ts.isoformat() if p.ts else None,
            "lat": p.lat,
            "lon": p.lon,
            "accuracy_m": p.accuracy_m,
            "kind": p.kind,
            "session_id": p.session_id,
        })
    return jsonify({"device_id": dev.public_id, "user_id": dev.user_id, "items": out})


@bp.get("/api/tracker/admin/device/<string:device_id>/alerts")
def api_admin_device_alerts(device_id: str):
    """Алёрты по конкретному устройству (для /admin/devices/<id>).

    params:
      - limit (default 200, max 1000)
      - hours (default 72): окно по updated_at
      - active=all|1|0 : фильтр по активности (по умолчанию all)
    """
    require_admin("viewer")
    dev = TrackerDevice.query.filter_by(public_id=device_id).first()
    if not dev:
        return _err('bad_request', 'not found', 404)

    frm, to = _get_time_range_from_args()

    try:
        limit = int(request.args.get("limit", 200))
    except Exception:
        limit = 200
    limit = max(50, min(limit, 1000))

    try:
        offset = int(request.args.get("offset", 0))
    except Exception:
        offset = 0
    offset = max(0, offset)

    hours = request.args.get("hours")
    cutoff = None
    if hours is None:
        hours = "72"
    try:
        cutoff = _utcnow() - timedelta(hours=float(hours))
    except Exception:
        cutoff = None

    active = str(request.args.get("active", "all")).strip().lower()
    q = TrackerAlert.query.filter(TrackerAlert.device_id == dev.public_id)

    if active in ("1", "true", "active"):
        q = q.filter_by(is_active=True)
    elif active in ("0", "false", "inactive", "closed"):
        q = q.filter_by(is_active=False)

    if frm is not None:
        q = q.filter(TrackerAlert.updated_at >= frm)
    if to is not None:
        q = q.filter(TrackerAlert.updated_at <= to)
    elif cutoff is not None:
        q = q.filter(TrackerAlert.updated_at >= cutoff)

    rows = q.order_by(TrackerAlert.updated_at.desc()).offset(offset).limit(limit).all()

    return jsonify({
        "device_id": dev.public_id,
        "user_id": dev.user_id,
        "items": [r.to_dict() for r in rows],
    })
@bp.get("/api/tracker/admin/device/<string:device_id>/export/health.csv")
def api_admin_device_export_health_csv(device_id: str):
    """Экспорт health_log в CSV (удобно для разбора/отчётов)."""
    require_admin("viewer")
    dev = TrackerDevice.query.filter_by(public_id=device_id).first()
    if not dev:
        return _err('bad_request', 'not found', 404)

    import csv
    from io import StringIO
    from flask import Response

    # filters
    try:
        hours = float(request.args.get('hours') or 0)
    except Exception:
        hours = 0
    try:
        limit = int(request.args.get('limit', 5000))
    except Exception:
        limit = 5000
    limit = max(1, min(limit, 20000))
    frm, to = _get_time_range_from_args()

    cutoff = None
    if (frm is None and to is None) and hours and hours > 0:
        cutoff = _utcnow() - timedelta(hours=hours)

    q = TrackerDeviceHealthLog.query.filter_by(device_id=dev.public_id)
    if frm is not None:
        q = q.filter(TrackerDeviceHealthLog.ts >= frm)
    if to is not None:
        q = q.filter(TrackerDeviceHealthLog.ts <= to)
    elif cutoff is not None:
        q = q.filter(TrackerDeviceHealthLog.ts >= cutoff)
    rows = q.order_by(TrackerDeviceHealthLog.ts.desc()).limit(limit).all()
    buf = StringIO()
    w = csv.writer(buf)
    w.writerow(["ts", "battery_pct", "is_charging", "net", "gps", "accuracy_m", "queue_size", "tracking_on", "last_error", "device_model", "os_version", "app_version"])
    for r in rows[::-1]:
        w.writerow([
            r.ts.isoformat() if r.ts else "",
            r.battery_pct,
            int(r.is_charging) if r.is_charging is not None else "",
            r.net,
            r.gps,
            r.accuracy_m,
            r.queue_size,
            int(r.tracking_on) if r.tracking_on is not None else "",
            r.last_error,
            r.device_model,
            r.os_version,
            r.app_version,
        ])
    resp = Response(buf.getvalue(), mimetype="text/csv; charset=utf-8")
    resp.headers["Content-Disposition"] = f"attachment; filename=health_{dev.public_id}.csv"
    _audit('EXPORT_HEALTH_CSV', device_id=dev.public_id, user_id=dev.user_id, payload={'rows': len(rows)})
    return resp


@bp.get("/api/tracker/admin/device/<string:device_id>/export/points.csv")
def api_admin_device_export_points_csv(device_id: str):
    """Экспорт последних точек TrackingPoint в CSV."""
    require_admin("viewer")
    dev = TrackerDevice.query.filter_by(public_id=device_id).first()
    if not dev:
        return _err('bad_request', 'not found', 404)

    import csv
    from io import StringIO
    from flask import Response

    # filters
    frm, to = _get_time_range_from_args()
    try:
        hours = float(request.args.get('hours') or 0)
    except Exception:
        hours = 0.0
    try:
        limit = int(request.args.get('limit', 5000))
    except Exception:
        limit = 5000
    limit = max(1, min(limit, 20000))

    cutoff = None
    if (frm is None and to is None) and hours and hours > 0:
        cutoff = _utcnow() - timedelta(hours=hours)


    q = TrackingPoint.query.filter(TrackingPoint.user_id == dev.user_id)
    if frm is not None:
        q = q.filter(TrackingPoint.ts >= frm)
    if to is not None:
        q = q.filter(TrackingPoint.ts <= to)
    elif cutoff is not None:
        q = q.filter(TrackingPoint.ts >= cutoff)
    pts = q.order_by(TrackingPoint.ts.desc()).limit(limit).all()
    buf = StringIO()
    w = csv.writer(buf)
    w.writerow(["ts", "lat", "lon", "accuracy_m", "kind", "session_id"])
    for p in pts[::-1]:
        w.writerow([
            p.ts.isoformat() if p.ts else "",
            p.lat,
            p.lon,
            p.accuracy_m,
            p.kind,
            p.session_id,
        ])
    resp = Response(buf.getvalue(), mimetype="text/csv; charset=utf-8")
    resp.headers["Content-Disposition"] = f"attachment; filename=points_{dev.public_id}.csv"
    _audit('EXPORT_POINTS_CSV', device_id=dev.public_id, user_id=dev.user_id, payload={'rows': len(pts)})
    return resp




@bp.get("/api/tracker/admin/device/<string:device_id>/export/points.gpx")
def api_admin_device_export_points_gpx(device_id: str):
    """Экспорт трека в GPX (по точкам TrackingPoint)."""
    require_admin("viewer")
    dev = TrackerDevice.query.filter_by(public_id=device_id).first()
    if not dev:
        return _err('bad_request', 'not found', 404)

    from flask import Response
    from xml.sax.saxutils import escape as _xml_escape

    frm, to = _get_time_range_from_args()

    try:
        hours = float(request.args.get('hours') or 0)
    except Exception:
        hours = 0
    try:
        limit = int(request.args.get('limit', 20000))
    except Exception:
        limit = 20000
    limit = max(1, min(limit, 50000))
    cutoff = None
    if (frm is None and to is None) and hours and hours > 0:
        cutoff = _utcnow() - timedelta(hours=hours)

    q = TrackingPoint.query.filter(TrackingPoint.user_id == dev.user_id)
    if frm is not None:
        q = q.filter(TrackingPoint.ts >= frm)
    if to is not None:
        q = q.filter(TrackingPoint.ts <= to)
    elif cutoff is not None:
        q = q.filter(TrackingPoint.ts >= cutoff)
    pts = list(reversed(q.order_by(TrackingPoint.ts.desc()).limit(limit).all()))

    def _ts(t):
        if not t:
            return ""
        s = t.isoformat()
        # если naive — считаем UTC
        if t.tzinfo is None and not s.endswith('Z'):
            s += 'Z'
        return s

    name = _xml_escape(dev.label or dev.public_id or "track")
    parts = []
    parts.append('<?xml version="1.0" encoding="UTF-8"?>')
    parts.append('<gpx version="1.1" creator="Map v12" xmlns="http://www.topografix.com/GPX/1/1">')
    parts.append(f'<metadata><name>{name}</name></metadata>')
    parts.append(f'<trk><name>{name}</name><trkseg>')
    for p in pts:
        if p.lat is None or p.lon is None:
            continue
        parts.append(f'<trkpt lat="{p.lat}" lon="{p.lon}">')
        ts = _ts(p.ts)
        if ts:
            parts.append(f'<time>{_xml_escape(ts)}</time>')
        # сохраняем accuracy в extensions (не стандарт GPX, но полезно)
        if getattr(p, 'accuracy_m', None) is not None:
            parts.append('<extensions>')
            parts.append(f'<accuracy_m>{_xml_escape(str(p.accuracy_m))}</accuracy_m>')
            parts.append('</extensions>')
        parts.append('</trkpt>')
    parts.append('</trkseg></trk></gpx>')

    resp = Response("\n".join(parts), mimetype="application/gpx+xml; charset=utf-8")
    resp.headers["Content-Disposition"] = f"attachment; filename=points_{dev.public_id}.gpx"
    _audit('EXPORT_POINTS_GPX', device_id=dev.public_id, user_id=dev.user_id, payload={'rows': len(pts), 'hours': hours})
    return resp


@bp.get("/api/tracker/admin/device/<string:device_id>/export/alerts.csv")
def api_admin_device_export_alerts_csv(device_id: str):
    """Экспорт алёртов устройства в CSV (история за период)."""
    require_admin("viewer")
    dev = TrackerDevice.query.filter_by(public_id=device_id).first()
    if not dev:
        return _err('bad_request', 'not found', 404)

    frm, to = _get_time_range_from_args()

    import csv
    from io import StringIO
    from flask import Response

    try:
        hours = float(request.args.get('hours') or 72)
    except Exception:
        hours = 72
    try:
        limit = int(request.args.get('limit', 5000))
    except Exception:
        limit = 5000
    limit = max(1, min(limit, 50000))
    cutoff = (_utcnow() - timedelta(hours=hours)) if hours and hours > 0 else None

    active = str(request.args.get("active", "all")).strip().lower()
    q = TrackerAlert.query.filter(TrackerAlert.device_id == dev.public_id)

    if active in ("1", "true", "active"):
        q = q.filter_by(is_active=True)
    elif active in ("0", "false", "inactive", "closed"):
        q = q.filter_by(is_active=False)

    if frm is not None:
        q = q.filter(TrackerAlert.updated_at >= frm)
    if to is not None:
        q = q.filter(TrackerAlert.updated_at <= to)
    elif cutoff is not None:
        q = q.filter(TrackerAlert.updated_at >= cutoff)

    rows = q.order_by(TrackerAlert.updated_at.desc()).limit(limit).all()

    buf = StringIO()
    w = csv.writer(buf)
    w.writerow(["updated_at", "created_at", "kind", "severity", "is_active", "acked_at", "closed_at", "message", "details", "payload_json", "user_id"])
    for r in rows[::-1]:
        try:
            payload_json = json.dumps(r.payload or {}, ensure_ascii=False)
        except Exception:
            payload_json = ""
        w.writerow([
            r.updated_at.isoformat() if r.updated_at else "",
            r.created_at.isoformat() if r.created_at else "",
            r.kind,
            r.severity,
            int(r.is_active) if r.is_active is not None else "",
            r.acked_at.isoformat() if r.acked_at else "",
            r.closed_at.isoformat() if r.closed_at else "",
            r.message,
            r.details,
            payload_json,
            r.user_id,
        ])

    resp = Response(buf.getvalue(), mimetype="text/csv; charset=utf-8")
    resp.headers["Content-Disposition"] = f"attachment; filename=alerts_{dev.public_id}.csv"
    _audit('EXPORT_ALERTS_CSV', device_id=dev.public_id, user_id=dev.user_id, payload={'rows': len(rows), 'hours': hours, 'active': active})
    return resp

@bp.get('/api/tracker/admin/alerts')
def api_admin_alerts():
    """Список алёртов по трекеру.

    Параметры:
      - active=1|0 : только активные (по умолчанию 1)
      - limit: по умолчанию 200
    """
    require_admin("viewer")
    active = str(request.args.get('active', '1')).strip().lower() not in ('0', 'false')
    limit = 200
    try:
        limit = max(50, min(1000, int(request.args.get('limit', '200'))))
    except Exception:
        limit = 200

    offset = 0
    try:
        offset = max(0, int(request.args.get('offset', '0')))
    except Exception:
        offset = 0

    q = TrackerAlert.query
    if active:
        q = q.filter_by(is_active=True)
    rows = q.order_by(TrackerAlert.updated_at.desc()).offset(offset).limit(limit).all()
    return jsonify([r.to_dict() for r in rows])


@bp.post('/api/tracker/admin/alerts/<int:alert_id>/ack')
def api_admin_alert_ack(alert_id: int):
    require_admin()
    row = TrackerAlert.query.get(alert_id)
    if not row:
        return _err('bad_request', 'not found', 404)

    if row.acked_at is None:
        by = (request.args.get('by') or '').strip() or None
        admin = get_current_admin()
        if admin:
            by = by or getattr(admin, 'username', None)
        row.acked_at = _utcnow()
        row.acked_by = by
        row.updated_at = row.acked_at
        db.session.commit()
        _audit('ACK_ALERT', device_id=row.device_id, user_id=row.user_id, payload={'alert_id': row.id, 'kind': row.kind})
        broadcast_event_sync('tracker_alert_acked', row.to_dict())

    return _ok({'alert': row.to_dict()})


@bp.post('/api/tracker/admin/alerts/<int:alert_id>/close')
def api_admin_alert_close(alert_id: int):
    require_admin()
    row = TrackerAlert.query.get(alert_id)
    if not row:
        return _err('bad_request', 'not found', 404)

    if row.is_active:
        by = (request.args.get('by') or '').strip() or None
        admin = get_current_admin()
        if admin:
            by = by or getattr(admin, 'username', None)
        row.is_active = False
        row.closed_at = _utcnow()
        row.closed_by = by
        row.updated_at = row.closed_at
        db.session.commit()
        _audit('CLOSE_ALERT', device_id=row.device_id, user_id=row.user_id, payload={'alert_id': row.id, 'kind': row.kind})
        broadcast_event_sync('tracker_alert_closed', {'kind': row.kind, 'device_id': row.device_id, 'user_id': row.user_id, 'alert_id': row.id})

    return _ok({'alert': row.to_dict()})


@bp.get('/api/tracker/admin/problems')
def api_admin_tracker_problems():
    """Агрегированный срез проблем по всем устройствам.

    Удобно для UI (одна ручка вместо N запросов).
    """
    require_admin("viewer")

    # Обновляем алёрты прямо перед отдачей (чтобы UI видел свежий статус
    # даже если фоновой scheduler отключён или процесс только что запустился).
    try:
        tracker_alerts_tick(current_app)
    except Exception:
        try:
            current_app.logger.exception('tracker_alerts_tick failed')
        except Exception:
            pass

    # Берём активные алёрты
    alerts = TrackerAlert.query.filter_by(is_active=True).order_by(TrackerAlert.updated_at.desc()).limit(1000).all()
    by_device: Dict[str, Dict[str, Any]] = {}
    for a in alerts:
        did = a.device_id or 'unknown'
        by_device.setdefault(did, {'device_id': did, 'user_id': a.user_id, 'alerts': []})
        by_device[did]['alerts'].append(a.to_dict())

    return jsonify({'server_time': _utcnow().isoformat(), 'devices': list(by_device.values())})


# -------------------------
# Pair (public): exchange one-time code -> device token
# -------------------------

@bp.post("/api/tracker/pair")
def api_pair():
    data = request.get_json(silent=True) or {}
    code = str(data.get("code") or "").strip()
    if not (code.isdigit() and len(code) == 6):
        return _err('bad_request', 'code must be 6 digits', 400)

    code_hash = _sha256_hex(code)
    ip = _client_ip()
    bad = _rate_limit_pair(ip, code_hash)
    if bad:
        return bad

    pc = TrackerPairCode.query.filter_by(code_hash=code_hash).first()
    if not pc or pc.used_at is not None or pc.expires_at <= _utcnow():
        return _err('invalid_request', 'invalid or expired code', 403)

    # generate device token (return plain, store hash)
    token = secrets.token_hex(32)
    token_hash = _sha256_hex(token)

    # create device
    public_id = secrets.token_hex(4)  # 8 hex chars

    # Bind tracker device to Telegram user_id when pairing code was issued via bootstrap/connect.
    # This makes DutyShift(user_id=TG_ID) and TrackingSession/TrackingPoint(user_id=TG_ID) match,
    # so Command Center can show live tracking for the officer.
    user_id = None

    # 1) explicit claim from client (optional; allowed only for numeric ids)
    claim_uid = (data.get('tg_user_id') or data.get('user_id') or '').strip()
    if claim_uid.isdigit():
        user_id = claim_uid[:32]

    # 2) resolve from bootstrap token table by pair_code
    if not user_id:
        try:
            bt = TrackerBootstrapToken.query.filter_by(pair_code=code).order_by(TrackerBootstrapToken.created_at.desc()).first()
        except Exception:
            bt = None
        if bt and (bt.tg_user_id or '').strip().isdigit():
            user_id = str(bt.tg_user_id).strip()[:32]

    # 3) fallback (standalone tracker)
    if not user_id:
        user_id = ("DT-" + public_id)[:32]

    # Auto-revoke previously paired devices for the same user_id (keep only one active device).
    # Optional toggle: AUTO_REVOKE_ON_PAIR (default 1).
    # This prevents Command Center from "sticking" to old DeviceHealth after re-pairing.
    revoked_public_ids = []
    try:
        do_auto_revoke = bool(current_app.config.get('AUTO_REVOKE_ON_PAIR', True))
        if do_auto_revoke and user_id:
            old_devs = TrackerDevice.query.filter_by(user_id=user_id, is_revoked=False).all()
            if old_devs:
                for od in old_devs:
                    od.is_revoked = True
                    revoked_public_ids.append(od.public_id)

                # close active tracking session for this user_id (same logic as manual revoke)
                sess = TrackingSession.query.filter_by(user_id=user_id, ended_at=None).order_by(TrackingSession.started_at.desc()).first()
                if sess:
                    sess.ended_at = _utcnow()
                    sess.is_active = False
    except Exception:
        revoked_public_ids = []

    dev = TrackerDevice(
        public_id=public_id,
        token_hash=token_hash,
        is_revoked=False,
        created_at=_utcnow(),
        last_seen_at=_utcnow(),
        label=pc.label,
        profile_json=None,
        user_id=user_id,
    )
    pc.used_at = _utcnow()

    db.session.add(dev)
    db.session.commit()

    # notify admin UI
    broadcast_event_sync("tracker_paired", {"device_id": dev.public_id, "user_id": dev.user_id, "label": dev.label})

    # Inform UI that previous devices were revoked (if any)
    for rid in revoked_public_ids:
        try:
            _audit('AUTO_REVOKE_DEVICE', device_id=rid, user_id=dev.user_id, payload={'reason': 'paired_new_device', 'ip': _client_ip()})
        except Exception:
            pass
        broadcast_event_sync("tracker_device_updated", {"device_id": rid, "is_revoked": True})

    return _ok({'device_token': token, 'device_id': dev.public_id, 'user_id': dev.user_id, 'label': dev.label})


# -------------------------
# Device endpoints
# -------------------------

@bp.post("/api/tracker/profile")
def api_profile():
    dev, err = _require_device()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    # сохраняем только ожидаемые поля (чтобы не заливать мусор)
    profile = {
        "full_name": (data.get("full_name") or "").strip()[:128],
        "duty_number": (data.get("duty_number") or "").strip()[:64],
        "unit": (data.get("unit") or "").strip()[:128],
        "position": (data.get("position") or "").strip()[:128],
        "rank": (data.get("rank") or "").strip()[:64],
        "phone": (data.get("phone") or "").strip()[:64],
    }
    # выбрасываем пустые
    profile = {k: v for k, v in profile.items() if v}

    dev.profile_json = json.dumps(profile, ensure_ascii=False)
    # авто-label (если не задан)
    if not dev.label:
        dev.label = profile.get("duty_number") or profile.get("full_name") or dev.public_id

    db.session.commit()

    broadcast_event_sync("tracker_profile", {"device_id": dev.public_id, "user_id": dev.user_id, "label": dev.label, "profile": profile})
    return _ok({'label': dev.label, 'profile': profile, 'device_id': dev.public_id})


def _get_or_create_active_shift_for_device(dev: TrackerDevice, lat: Optional[float] = None, lon: Optional[float] = None) -> DutyShift:
    sh = DutyShift.query.filter_by(user_id=dev.user_id, ended_at=None).order_by(DutyShift.started_at.desc()).first()
    if sh:
        if dev.label and not sh.unit_label:
            sh.unit_label = dev.label[:64]
        db.session.commit()
        return sh

    sh = DutyShift(
        user_id=dev.user_id,
        unit_label=(dev.label or dev.public_id)[:64],
        started_at=_utcnow(),
        start_lat=lat,
        start_lon=lon,
    )
    db.session.add(sh)
    db.session.commit()
    return sh


def _create_app_session(dev: TrackerDevice, shift_id: int) -> TrackingSession:
    # закроем предыдущую активную app-сессию (на всякий)
    old = TrackingSession.query.filter_by(user_id=dev.user_id, message_id=None, ended_at=None).order_by(TrackingSession.started_at.desc()).first()
    if old:
        old.ended_at = _utcnow()
        old.is_active = False
        db.session.commit()

    sess = TrackingSession(
        user_id=dev.user_id,
        shift_id=shift_id,
        message_id=None,
        started_at=_utcnow(),
        ended_at=None,
        is_active=True,
        last_lat=None,
        last_lon=None,
        last_at=None,
    )
    db.session.add(sess)
    db.session.commit()
    return sess


@bp.post("/api/tracker/start")
def api_start() -> tuple[Response, int] | Response:
    dev, err = _require_device()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    lat = data.get("lat"); lon = data.get("lon")
    try:
        lat = float(lat) if lat is not None else None
        lon = float(lon) if lon is not None else None
    except Exception:
        lat = lon = None

    # Pydantic validation for telemetry-like payload (optional when coordinates are provided)
    if lat is not None or lon is not None:
        try:
            telemetry = TelemetryCreateSchema.model_validate({
                'lon': lon,
                'lat': lat,
                'alt': data.get('alt'),
                'battery': data.get('battery') if data.get('battery') is not None else data.get('battery_pct'),
                'status': (data.get('status') or 'start'),
                'user_id': dev.user_id,
            })
            lat = telemetry.lat
            lon = telemetry.lon
        except ValidationError as e:
            return jsonify({"error": "Validation failed", "details": e.errors()}), 400

    sh = _get_or_create_active_shift_for_device(dev, lat=lat, lon=lon)
    sess = _create_app_session(dev, shift_id=sh.id)

    broadcast_event_sync("tracking_started", {"device_id": dev.public_id, "user_id": dev.user_id, "shift_id": sh.id, "session_id": sess.id, "message_id": None, "label": sh.unit_label})
    return _ok({'shift_id': sh.id, 'session_id': sess.id, 'user_id': dev.user_id, 'device_id': dev.public_id, 'label': sh.unit_label})


@bp.post("/api/tracker/points")
def api_points():
    dev, err = _require_device()
    if err:
        return err

    rl = _rl_points(dev)
    if rl:
        return rl

    data = request.get_json(silent=True) or {}
    points = data.get("points") or []
    session_id = data.get("session_id")

    # определим активную сессию
    sess = None
    if session_id:
        # Если клиент прислал session_id — мы ведём себя строго: либо это активная
        # сессия, либо возвращаем 409 (чтобы клиент мог заново сделать /start).
        try:
            sess = TrackingSession.query.filter_by(id=int(session_id), user_id=dev.user_id, ended_at=None).first()
        except Exception:
            sess = None
        if not sess:
            active = TrackingSession.query.filter_by(user_id=dev.user_id, message_id=None, ended_at=None).order_by(TrackingSession.started_at.desc()).first()
            return _err(
                'session_inactive',
                'Provided session_id is not active. Call /api/tracker/start again.',
                409,
                details={'active_session_id': (active.id if active else None)},
            )

    if not sess:
        sess = TrackingSession.query.filter_by(user_id=dev.user_id, message_id=None, ended_at=None).order_by(TrackingSession.started_at.desc()).first()

    if not sess:
        # если смена не стартовала, создадим минимально
        sh = _get_or_create_active_shift_for_device(dev)
        sess = _create_app_session(dev, shift_id=sh.id)

    accepted = 0
    dedup = 0
    rejected = 0
    first_ts = None
    last_ts = None

    # лимит размера пачки
    if isinstance(points, list) and len(points) > 500:
        points = points[:500]

    # заранее соберём список ts для дедупа
    ts_list: List[datetime] = []
    norm_points: List[Dict[str, Any]] = []
    for p in points if isinstance(points, list) else []:
        if not isinstance(p, dict):
            rejected += 1
            continue

        # lat/lon
        try:
            lat_raw = p.get("lat", None)
            lon_raw = p.get("lon", None)
            if lat_raw is None:
                lat_raw = p.get("latitude", None)
            if lon_raw is None:
                lon_raw = p.get("longitude", None)
            lat = float(lat_raw)
            lon = float(lon_raw)
        except Exception:
            rejected += 1
            continue

        # диапазоны координат
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            rejected += 1
            continue

        # accuracy (метры)
        acc = p.get("acc") if "acc" in p else p.get("accuracy_m")
        try:
            acc = float(acc) if acc is not None else None
        except Exception:
            acc = None
        if acc is not None and (acc < 0 or acc > 5000):
            acc = None



        # speed (m/s) + bearing (deg) (optional)
        spd = p.get("speed_mps") if "speed_mps" in p else p.get("speed")
        if spd is None:
            spd = p.get("spd")
        try:
            spd = float(spd) if spd is not None else None
        except Exception:
            spd = None
        if spd is not None and (spd < 0 or spd > 200):
            spd = None

        brg = p.get("bearing_deg") if "bearing_deg" in p else p.get("bearing")
        if brg is None:
            brg = p.get("heading")
        try:
            brg = float(brg) if brg is not None else None
        except Exception:
            brg = None
        if brg is not None and (brg < 0 or brg > 360):
            brg = None
        # ts
        ts_raw = p.get("ts") or p.get("timestamp") or p.get("time")
        if ts_raw is None:
            rejected += 1
            continue

        try:
            if isinstance(ts_raw, (int, float)):
                tsf = float(ts_raw)
                # поддержка ms epoch
                ts = datetime.utcfromtimestamp(tsf / 1000.0 if tsf > 10_000_000_000 else tsf)
            else:
                ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            rejected += 1
            continue

        # защита от будущего времени
        if ts > (_utcnow() + timedelta(minutes=10)):
            rejected += 1
            continue

        flags: List[str] = []
        calc_speed = None
        if norm_points:
            try:
                prev = norm_points[-1]
                dt = (ts - prev["ts"]).total_seconds()
                if dt > 0:
                    dist_m = _haversine_m(prev["lat"], prev["lon"], lat, lon)
                    speed = dist_m / dt
                    calc_speed = speed
                    # >80 м/с (~288 км/ч) — подозрительный прыжок GPS
                    if speed > 80:
                        flags.append("jump")
            except Exception:
                pass

        if spd is None and calc_speed is not None and 0 <= calc_speed <= 120:
            spd = calc_speed

        ts_list.append(ts)
        norm_points.append({"lat": lat, "lon": lon, "ts": ts, "acc": acc, "speed": spd, "bearing": brg, "flags": flags})

    existing_ts = set()
    if ts_list:
        rows = TrackingPoint.query.with_entities(TrackingPoint.ts).filter(TrackingPoint.session_id == sess.id, TrackingPoint.ts.in_(ts_list)).all()
        existing_ts = set([r[0] for r in rows])

    if ts_list:
        first_ts = min(ts_list).isoformat()
        last_ts = max(ts_list).isoformat()


    for p in norm_points:
        if p["ts"] in existing_ts:
            dedup += 1
            continue
        try:
            with db.session.begin_nested():
                tp = TrackingPoint(
                    user_id=dev.user_id,
                    session_id=sess.id,
                    ts=p["ts"],
                    lat=p["lat"],
                    lon=p["lon"],
                    kind="app",
                    accuracy_m=p["acc"],
                    raw_json=json.dumps({"src": "app", "acc": p["acc"], "speed_mps": p.get("speed"), "bearing_deg": p.get("bearing"), "flags": p.get("flags") or []}, ensure_ascii=False),
                )
                db.session.add(tp)
                db.session.flush()
            accepted += 1
        except IntegrityError:
            db.session.rollback()
            dedup += 1
            continue

        # обновим last
        sess.last_lat = p["lat"]
        sess.last_lon = p["lon"]
        sess.last_at = p["ts"]
        sess.is_active = True

        # событие в realtime (шлём по одной, так легче на фронте)
        broadcast_event_sync("tracking_point", {
            "device_id": dev.public_id,
            "user_id": dev.user_id,
            "shift_id": sess.shift_id,
            "session_id": sess.id,
            "lat": p["lat"],
            "lon": p["lon"],
            "ts": p["ts"].isoformat(),
            "accuracy_m": p["acc"],
            "speed_mps": p.get("speed"),
            "bearing_deg": p.get("bearing"),
            "flags": p.get("flags") or [],
            "source": "app",
        })

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()

    return _ok({'session_id': sess.id, 'accepted': accepted, 'dedup': dedup, 'rejected': rejected, 'first_ts': first_ts, 'last_ts': last_ts})


@bp.post("/api/tracker/stop")
def api_stop():
    dev, err = _require_device()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id")

    sess = None
    if session_id:
        try:
            sess = TrackingSession.query.filter_by(id=int(session_id), user_id=dev.user_id).first()
        except Exception:
            sess = None
    if not sess:
        sess = TrackingSession.query.filter_by(user_id=dev.user_id, message_id=None, ended_at=None).order_by(TrackingSession.started_at.desc()).first()

    if not sess or sess.ended_at is not None:
        return _ok({'message': 'no_active_session'})

    sess.ended_at = _utcnow()
    sess.is_active = False
    db.session.commit()

    broadcast_event_sync("tracking_stopped", {"device_id": dev.public_id, "user_id": dev.user_id, "shift_id": sess.shift_id, "session_id": sess.id, "message_id": None, "source": "app"})
    return _ok({'session_id': sess.id})


# -------------------------
# SOS (Android)
# -------------------------

def _get_active_app_session(dev: TrackerDevice, session_id: Optional[int] = None) -> Optional[TrackingSession]:
    sess = None
    if session_id is not None:
        try:
            sess = TrackingSession.query.filter_by(id=int(session_id), user_id=dev.user_id).first()
        except Exception:
            sess = None
    if not sess:
        sess = TrackingSession.query.filter_by(user_id=dev.user_id, message_id=None, ended_at=None).order_by(TrackingSession.started_at.desc()).first()
    return sess


def _get_last_point_for_session(session_id: int) -> Optional[TrackingPoint]:
    try:
        return TrackingPoint.query.filter_by(session_id=session_id).order_by(TrackingPoint.ts.desc()).first()
    except Exception:
        return None


@bp.post("/api/tracker/sos")
def api_sos():
    """SOS от устройства.

    Тело запроса (все поля опциональны, кроме note):
      - lat, lon, accuracy_m
      - note (строка до 256)
      - session_id (если хочешь привязать явно)

    Если координаты не переданы, попробуем взять из активной сессии (last_lat/lon) или последней точки.
    """
    dev, err = _require_device()
    if err:
        return err

    rl = _rl_sos(dev)
    if rl:
        return rl

    data = request.get_json(silent=True) or {}
    note = (data.get("note") or "").strip()[:256] or None

    session_id = data.get("session_id")
    sess = _get_active_app_session(dev, session_id=session_id)

    # coords
    lat = data.get("lat"); lon = data.get("lon")
    acc = data.get("accuracy_m") if "accuracy_m" in data else data.get("acc")
    try:
        lat = float(lat) if lat is not None else None
        lon = float(lon) if lon is not None else None
    except Exception:
        lat = lon = None
    try:
        acc = float(acc) if acc is not None else None
    except Exception:
        acc = None

    if (lat is None or lon is None) and sess:
        if sess.last_lat is not None and sess.last_lon is not None:
            lat = float(sess.last_lat)
            lon = float(sess.last_lon)
        else:
            lp = _get_last_point_for_session(sess.id)
            if lp and lp.lat is not None and lp.lon is not None:
                lat = float(lp.lat)
                lon = float(lp.lon)

    if lat is None or lon is None:
        return _err('need_location', 'No coordinates provided and no last location available', 409)

    # ensure shift exists
    sh = _get_or_create_active_shift_for_device(dev, lat=lat, lon=lon)

    alert = SosAlert(
        user_id=dev.user_id,
        shift_id=sh.id if sh else None,
        session_id=sess.id if sess else None,
        unit_label=(sh.unit_label if sh else (dev.label or dev.public_id))[:64],
        created_at=_utcnow(),
        status="open",
        lat=float(lat),
        lon=float(lon),
        accuracy_m=acc,
        note=note,
    )

    db.session.add(alert)
    db.session.commit()

    # realtime alert for admin overlay
    broadcast_event_sync("sos_created", alert.to_dict())
    return _ok({'sos_id': alert.id, 'sos': alert.to_dict()})


@bp.post("/api/tracker/sos/last")
def api_sos_last():
    """SOS по последней известной точке (без передачи координат)."""
    dev, err = _require_device()
    if err:
        return err

    rl = _rl_sos(dev)
    if rl:
        return rl

    data = request.get_json(silent=True) or {}
    note = (data.get("note") or "").strip()[:256] or None
    session_id = data.get("session_id")
    sess = _get_active_app_session(dev, session_id=session_id)

    lat = lon = None
    acc = None

    if sess and sess.last_lat is not None and sess.last_lon is not None:
        lat = float(sess.last_lat)
        lon = float(sess.last_lon)
    if (lat is None or lon is None) and sess:
        lp = _get_last_point_for_session(sess.id)
        if lp and lp.lat is not None and lp.lon is not None:
            lat = float(lp.lat)
            lon = float(lp.lon)
            acc = lp.accuracy_m

    if lat is None or lon is None:
        return _err('need_location', 'No last location available', 409)

    sh = _get_or_create_active_shift_for_device(dev, lat=lat, lon=lon)
    alert = SosAlert(
        user_id=dev.user_id,
        shift_id=sh.id if sh else None,
        session_id=sess.id if sess else None,
        unit_label=(sh.unit_label if sh else (dev.label or dev.public_id))[:64],
        created_at=_utcnow(),
        status="open",
        lat=float(lat),
        lon=float(lon),
        accuracy_m=acc,
        note=note,
    )
    db.session.add(alert)
    db.session.commit()

    broadcast_event_sync("sos_created", alert.to_dict())
    return _ok({'sos_id': alert.id, 'sos': alert.to_dict(), 'used_last': True})

@bp.get("/api/tracker/admin/metrics")
def api_admin_metrics():
    """Простые метрики (для панели/мониторинга)."""
    require_admin("viewer")
    now = _utcnow()

    # делаем best-effort tick алёртов, чтобы мониторинг видел свежее состояние
    try:
        tracker_alerts_tick(current_app)
    except Exception:
        try:
            current_app.logger.exception('tracker_alerts_tick failed')
        except Exception:
            pass

    total_devices = TrackerDevice.query.count()
    revoked_devices = TrackerDevice.query.filter_by(is_revoked=True).count()

    online_window_sec = int(os.environ.get("TRACKER_ONLINE_WINDOW_SEC", "60"))
    online_cutoff = now - timedelta(seconds=online_window_sec)
    online_devices = TrackerDevice.query.filter(TrackerDevice.last_seen_at != None, TrackerDevice.last_seen_at >= online_cutoff).count()

    active_alerts_q = TrackerAlert.query.filter_by(is_active=True)
    active_alerts = active_alerts_q.count()
    crit_alerts = active_alerts_q.filter_by(severity="crit").count()

    p_cutoff = now - timedelta(minutes=5)
    points_5m = TrackingPoint.query.filter(TrackingPoint.ts >= p_cutoff).count()

    # последние алёрты (20)
    recent_rows = TrackerAlert.query.order_by(TrackerAlert.updated_at.desc()).limit(20).all()
    active_sample_rows = TrackerAlert.query.filter_by(is_active=True).order_by(TrackerAlert.updated_at.desc()).limit(20).all()

    def _enrich(rows):
        ids = sorted({r.device_id for r in rows if r.device_id})
        dev_map = {}
        if ids:
            try:
                pairs = TrackerDevice.query.with_entities(TrackerDevice.public_id, TrackerDevice.label).filter(TrackerDevice.public_id.in_(ids)).all()
                dev_map = {pid: (lbl or pid) for pid, lbl in pairs}
            except Exception:
                dev_map = {}
        out = []
        for r in rows:
            d = r.to_dict()
            did = d.get('device_id')
            d['device_label'] = dev_map.get(did) if did else None
            out.append(d)
        return out

    return _ok({
        "generated_at": now.isoformat() + 'Z',
        "metrics": {
            "total_devices": total_devices,
            "online_devices": online_devices,
            "revoked_devices": revoked_devices,
            "active_alerts": active_alerts,
            "crit_alerts": crit_alerts,
            "points_last_5m": points_5m,
            "online_window_sec": online_window_sec,
        },
        "recent_alerts": _enrich(recent_rows),
        "active_alerts_sample": _enrich(active_sample_rows),
    })


@bp.get("/open/dutytracker")
def open_dutytracker_page():
    """Промежуточная HTTP-страница для открытия DutyTracker из Telegram.

    Telegram inline-кнопки поддерживают только http/https, поэтому мы выдаём страницу,
    которая сразу редиректит в dutytracker://... и даёт fallback-ссылки.

    Query:
      - token: bootstrap-token (одноразовый)
    """
    token = (request.args.get("token") or "").strip()
    # base_url берём из самого запроса (host_url), чтобы совпадал с тем, по чему реально открыли страницу
    base_url = (request.args.get("base_url") or request.host_url or "").strip().rstrip("/")

    if not token:
        return (
            "<h3>Missing token</h3><p>Откройте ссылку из бота заново (token обязателен).</p>",
            400,
            {"Content-Type": "text/html; charset=utf-8"},
        )

    deeplink = f"dutytracker://bootstrap?base_url={quote(base_url, safe='')}&token={quote(token, safe='')}"
    intent_link = (
        "intent://bootstrap"
        f"?base_url={quote(base_url, safe='')}&token={quote(token, safe='')}"
        "#Intent;scheme=dutytracker;package=com.mapv12.dutytracker;end"
    )

    html = f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>DutyTracker</title>
  <meta http-equiv="refresh" content="0;url={deeplink}">
  <style>
    body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;padding:16px;}}
    .box{{max-width:720px;margin:0 auto;}}
    .btn{{display:inline-block;padding:12px 14px;border-radius:10px;border:1px solid #444;text-decoration:none;margin:6px 0;}}
    code{{display:block;white-space:pre-wrap;word-break:break-all;background:#111;color:#eee;padding:10px;border-radius:10px;}}
  </style>
</head>
<body>
  <div class="box">
    <h2>Открываем DutyTracker…</h2>
    <p>Если приложение не открылось автоматически — нажмите одну из кнопок ниже.</p>

    <a class="btn" href="{intent_link}">Открыть DutyTracker (Intent)</a><br/>
    <a class="btn" href="{deeplink}">Открыть DutyTracker (Deep link)</a>

    <p style="margin-top:14px;">Ссылки для копирования:</p>
    <code>{deeplink}</code>
    <code>{intent_link}</code>

    <p style="margin-top:14px;">
      Важно: телефон должен видеть сервер по адресу <b>{base_url}</b> (Wi‑Fi/VPN + firewall).
    </p>
  </div>
  <script>
    // Дублируем попытку редиректа через JS (на некоторых WebView meta-refresh игнорируется)
    setTimeout(function(){{ window.location.href = "{deeplink}"; }}, 50);
  </script>
</body>
</html>"""

    return html, 200, {"Content-Type": "text/html; charset=utf-8"}
