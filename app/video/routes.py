"""Live/Archive video routes for Command Center.

Примечание: текущий проект использует Flask blueprints.
"""

from __future__ import annotations

import datetime as dt
import ftplib
import json
import os
import posixpath
import re
import socket
import subprocess
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import httpx
from flask import Response, jsonify, request, stream_with_context
from starlette.concurrency import run_in_threadpool

from .. import models
from . import bp
from app.extensions import db
from app.auth.decorators import jwt_or_api_required, require_audit_auth

# ===== ДОБАВЛЕННЫЕ ИМПОРТЫ ДЛЯ АУДИТА =====
import uuid
from datetime import datetime, timedelta
from celery_worker import run_audit_task, run_wifi_audit_task
from app.realtime.tokens import generate_websocket_token
# ===== КОНЕЦ ДОБАВЛЕННЫХ ИМПОРТОВ =====


def _extract_terminal_channel(channel_id: int) -> Tuple[Any, Any]:
    """Resolve (channel, terminal) from available DB models.

    Preferred: VideoChannel + Terminal models.
    Fallback: ObjectCamera + Object models.
    """
    video_channel_cls = getattr(models, "VideoChannel", None)
    terminal_cls = getattr(models, "Terminal", None)

    if video_channel_cls is not None:
        channel = video_channel_cls.query.get(channel_id)
        if not channel:
            return None, None
        terminal = getattr(channel, "terminal", None)
        if terminal is None and terminal_cls is not None:
            terminal_id = getattr(channel, "terminal_id", None)
            if terminal_id is not None:
                terminal = terminal_cls.query.get(terminal_id)
        return channel, terminal

    object_camera_cls = getattr(models, "ObjectCamera", None)
    if object_camera_cls is not None:
        channel = object_camera_cls.query.get(channel_id)
        if not channel:
            return None, None
        terminal = getattr(channel, "object", None)
        return channel, terminal

    return None, None


def _auth_payload(terminal: Any) -> Dict[str, Any]:
    raw = getattr(terminal, "auth_credentials", None)
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            return json.loads(raw)
        except Exception:
            return {}
    return {}


def _extract_creds(terminal: Any) -> Tuple[str, str]:
    data = _auth_payload(terminal)

    user = (
        data.get("user")
        or data.get("login")
        or ""
    )
    secret = (
        data.get("hash")
        or data.get("pass")
        or data.get("password")
        or ""
    )
    return str(user), str(secret)


def _terminal_ip(terminal: Any) -> Optional[str]:
    return (
        getattr(terminal, "ip", None)
        or getattr(terminal, "ip_address", None)
        or getattr(terminal, "host", None)
    )


def _resolve_terminal_by_id(terminal_id: int) -> Optional[Any]:
    terminal_cls = getattr(models, "Terminal", None)
    if terminal_cls is not None:
        return terminal_cls.query.get(terminal_id)

    object_cls = getattr(models, "Object", None)
    if object_cls is not None:
        return object_cls.query.get(terminal_id)

    return None


def _channel_prefix(channel: Any) -> str:
    raw = getattr(channel, "channel_number", None)
    if raw is None:
        raw = getattr(channel, "id", "")
    s = str(raw).strip()
    if not s:
        return ""
    if s.lower().startswith("cam"):
        return f"{s.lower()}_"
    if s.isdigit():
        return f"cam{int(s):02d}_"
    return f"{s.lower()}_"


def _parse_file_time(name: str) -> Optional[str]:
    m = re.search(r"(\d{8})[T_\-]?(\d{6})", name)
    if not m:
        return None
    try:
        ts = dt.datetime.strptime(f"{m.group(1)}{m.group(2)}", "%Y%m%d%H%M%S")
        return ts.isoformat()
    except Exception:
        return None


def _archive_root_path(terminal: Any) -> str:
    data = _auth_payload(terminal)
    return (
        getattr(terminal, "archive_root_path", None)
        or data.get("root_path")
        or data.get("archive_path")
        or os.environ.get("LEGACY_FTP_ROOT_PATH")
        or "0:/video1/Minsk_ul._Mendeleeva_30_/"
    )


def _list_ftp_archive(
    *,
    host: str,
    user: str,
    password: str,
    root_path: str,
    date: str,
    prefix: str,
) -> List[Dict[str, Any]]:
    ftp = ftplib.FTP()
    ftp.connect(host=host, timeout=15)
    ftp.login(user=user, passwd=password)
    try:
        date_dir = posixpath.join(root_path.rstrip("/"), date)
        entries: List[Tuple[str, int]] = []

        def _collector(line: str) -> None:
            # Expected format: "-rw-r--r-- 1 user group 12345 Jan 01 10:00 filename"
            parts = line.split(maxsplit=8)
            if len(parts) < 9:
                return
            size_raw = parts[4]
            name = parts[8]
            if not name.lower().startswith(prefix.lower()):
                return
            try:
                size = int(size_raw)
            except Exception:
                size = 0
            entries.append((name, size))

        try:
            ftp.cwd(date_dir)
        except ftplib.error_perm:
            return []

        ftp.retrlines("LIST", _collector)
        return [
            {
                "file_name": name,
                "size": size,
                "time": _parse_file_time(name),
            }
            for name, size in entries
        ]
    finally:
        try:
            ftp.quit()
        except Exception:
            ftp.close()


@bp.get("/live/<int:channel_id>")
def video_live_proxy(channel_id: int):
    channel, linked_terminal = _extract_terminal_channel(channel_id)
    if not channel:
        return jsonify({"error": "channel_or_terminal_not_found"}), 404

    terminal_id_raw = (request.args.get("terminal_id") or "").strip()
    if terminal_id_raw:
        try:
            terminal = _resolve_terminal_by_id(int(terminal_id_raw))
        except ValueError:
            return jsonify({"error": "invalid_terminal_id"}), 400
    else:
        terminal = linked_terminal

    if not terminal:
        return jsonify({"error": "terminal_not_found"}), 404

    terminal_type = (
        getattr(channel, "terminal_type", None)
        or getattr(terminal, "terminal_type", None)
        or ""
    )

    if str(terminal_type).upper() != "LEGACY_FTP":
        return jsonify({"error": "terminal_type_not_supported", "terminal_type": terminal_type}), 400

    ip = _terminal_ip(terminal)
    if not ip:
        return jsonify({"error": "terminal_ip_missing"}), 400

    user, password = _extract_creds(terminal)
    if not user:
        return jsonify({"error": "terminal_credentials_missing", "hint": "Set terminal.auth_credentials"}), 400
    channel_number = getattr(channel, "channel_number", None) or getattr(channel, "id", None)

    target_url = f"http://{ip}/stream/rtsp2mjpeg.php"
    params = {
        "get": 1,
        "user": user,
        "id": channel_number,
    }

    # Legacy servers often need cookie auth.
    cookies = {}
    if password:
        cookies = {
            "login": user,
            "password": password,
            # backward compatibility for legacy instances where field was called hash
            "hash": password,
        }

    def generate():
        with httpx.Client(timeout=None) as client:
            with client.stream("GET", target_url, params=params, cookies=cookies) as upstream:
                upstream.raise_for_status()
                for chunk in upstream.iter_bytes():
                    if chunk:
                        yield chunk

    return Response(
        stream_with_context(generate()),
        mimetype="multipart/x-mixed-replace; boundary=--myboundary",
        headers={"Cache-Control": "no-store"},
    )


@bp.get("/terminal/ping/<int:terminal_id>")
def terminal_ping(terminal_id: int):
    """Fast connectivity probe for terminal host/port."""
    terminal = _resolve_terminal_by_id(terminal_id)
    if not terminal:
        return jsonify({"ok": False, "error": "terminal_not_found"}), 404

    ip = _terminal_ip(terminal)
    if not ip:
        return jsonify({"ok": False, "error": "terminal_ip_missing"}), 400

    port = 80
    timeout_s = 1.5
    start = dt.datetime.now(tz=dt.timezone.utc)
    try:
        with socket.create_connection((ip, port), timeout=timeout_s):
            pass
        elapsed_ms = int((dt.datetime.now(tz=dt.timezone.utc) - start).total_seconds() * 1000)
        return jsonify({"ok": True, "terminal_id": terminal_id, "ip": ip, "port": port, "latency_ms": elapsed_ms}), 200
    except OSError as exc:
        return jsonify({"ok": False, "terminal_id": terminal_id, "ip": ip, "port": port, "error": str(exc)}), 200


@bp.get("/archive/index/<int:channel_id>")
async def video_archive_index(channel_id: int):
    date_value = (request.args.get("date") or "").strip()
    if not date_value:
        return jsonify({"error": "date_required", "expected": "YYYY-MM-DD"}), 400
    try:
        dt.datetime.strptime(date_value, "%Y-%m-%d")
    except ValueError:
        return jsonify({"error": "invalid_date", "expected": "YYYY-MM-DD"}), 400

    channel, terminal = _extract_terminal_channel(channel_id)
    if not channel or not terminal:
        return jsonify({"error": "channel_or_terminal_not_found"}), 404

    ip = _terminal_ip(terminal)
    if not ip:
        return jsonify({"error": "terminal_ip_missing"}), 400

    user, password = _extract_creds(terminal)
    if not user:
        return jsonify({"error": "terminal_credentials_missing", "hint": "Set terminal.auth_credentials"}), 400
    root_path = _archive_root_path(terminal)
    prefix = _channel_prefix(channel)

    files = await run_in_threadpool(
        _list_ftp_archive,
        host=ip,
        user=user,
        password=password,
        root_path=root_path,
        date=date_value,
        prefix=prefix,
    )

    return jsonify(files)


@bp.get("/archive/stream")
def video_archive_stream():
    file_path = (request.args.get("file_path") or "").strip()
    terminal_id_raw = (request.args.get("terminal_id") or "").strip()

    if not file_path or not terminal_id_raw:
        return jsonify({"error": "file_path_and_terminal_id_required"}), 400

    try:
        terminal_id = int(terminal_id_raw)
    except ValueError:
        return jsonify({"error": "invalid_terminal_id"}), 400

    terminal = _resolve_terminal_by_id(terminal_id)
    if not terminal:
        return jsonify({"error": "terminal_not_found"}), 404

    ip = _terminal_ip(terminal)
    if not ip:
        return jsonify({"error": "terminal_ip_missing"}), 400

    user, password = _extract_creds(terminal)
    if not user:
        return jsonify({"error": "terminal_credentials_missing", "hint": "Set terminal.auth_credentials"}), 400

    ftp_url = (
        f"ftp://{quote(user, safe='')}:{quote(password, safe='')}@{ip}/"
        f"{file_path.lstrip('/')}"
    )

    ffmpeg_cmd = [
        "ffmpeg",
        "-i",
        ftp_url,
        "-c",
        "copy",
        "-movflags",
        "frag_keyframe+empty_moov",
        "-f",
        "mp4",
        "pipe:1",
    ]

    def generate():
        proc = subprocess.Popen(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
        assert proc.stdout is not None
        try:
            while True:
                chunk = proc.stdout.read(64 * 1024)
                if not chunk:
                    break
                yield chunk
        finally:
            if proc.poll() is None:
                proc.kill()
            try:
                proc.wait(timeout=1)
            except Exception:
                pass

    return Response(
        stream_with_context(generate()),
        mimetype="video/mp4",
        headers={"Cache-Control": "no-store"},
    )


# ===== НОВЫЕ ЭНДПОИНТЫ ДЛЯ АУДИТА БЕЗОПАСНОСТИ =====
@bp.post("/audit/start")
@jwt_or_api_required
def start_audit():
    """Запускает аудит безопасности для указанной камеры."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON payload"}), 400
    
    ip = data.get("ip")
    port = data.get("port", 80)
    username = data.get("username", "admin")
    proxy_list = data.get("proxy_list")
    use_vuln_check = data.get("use_vuln_check", True)

    if not ip:
        return jsonify({"error": "ip required"}), 400

    task_id = str(uuid.uuid4())
    
    # Используем models.db для доступа к сессии (предполагается, что db доступен через models)
    result = models.CameraAuditResult(
        target_ip=ip,
        target_port=port,
        username=username,
        success=False,
        details={"task_id": task_id, "status": "pending"}
    )
    models.db.session.add(result)
    models.db.session.commit()
    
    run_audit_task.delay(
        task_id=task_id,
        ip=ip,
        port=port,
        username=username,
        proxy_list=proxy_list,
        use_vuln_check=use_vuln_check
    )
    
    return jsonify({"task_id": task_id, "status": "started"}), 202


@bp.get("/audit/result/<task_id>")
@jwt_or_api_required
def get_audit_result(task_id):
    """Возвращает результат аудита по ID задачи."""
    result = models.CameraAuditResult.query.filter(
        models.CameraAuditResult.details['task_id'].astext == task_id
    ).first()
    if not result:
        return jsonify({"error": "Task not found"}), 404
    
    return jsonify({
        "ip": result.target_ip,
        "success": result.success,
        "password": result.password_found,
        "method": result.method,
        "details": result.details
    })
# ===== КОНЕЦ НОВЫХ ЭНДПОИНТОВ =====


@bp.post("/wifi/audit/start")
@require_audit_auth
def start_wifi_audit():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON payload"}), 400

    bssid = data.get("bssid")
    essid = data.get("essid") or data.get("ssid")
    security_type = data.get("securityType")
    client_id = data.get("clientId")
    region = (data.get("region") or "ru").lower()

    if not bssid or not essid:
        return jsonify({"error": "bssid and essid required"}), 400

    # Кэширование: если для той же сети есть свежий completed результат — переиспользуем.
    fresh_cutoff = datetime.utcnow() - timedelta(hours=24)
    cached = (
        models.WifiAuditResult.query
        .filter(models.WifiAuditResult.bssid == bssid)
        .filter(models.WifiAuditResult.security_type == security_type)
        .filter(models.WifiAuditResult.updated_at.isnot(None))
        .filter(models.WifiAuditResult.updated_at >= fresh_cutoff)
        .order_by(models.WifiAuditResult.updated_at.desc())
        .first()
    )
    if cached and isinstance(cached.details, dict) and cached.details.get("status") == "completed":
        return jsonify({
            "taskId": cached.task_id,
            "status": "cached",
            "estimatedTime": int(cached.estimated_time_seconds or 0),
        }), 200

    task_id = str(uuid.uuid4())

    result = models.WifiAuditResult(
        task_id=task_id,
        client_id=client_id,
        bssid=bssid,
        essid=essid,
        security_type=security_type,
        is_vulnerable=False,
        estimated_time_seconds=300,
        progress=0,
        details={
            "status": "pending",
            "message": "Задача поставлена в очередь",
            "estimatedTime": 300,
            "progress": 0,
            "region": region,
        },
    )
    db.session.add(result)
    db.session.commit()

    run_wifi_audit_task.delay(
        task_id=task_id,
        bssid=bssid,
        essid=essid,
        security_type=security_type,
        region=region,
    )

    ws_channel = f"wifi_audit:{task_id}"
    ws_token = generate_websocket_token({"task_id": task_id, "channel": ws_channel}, expires_delta=timedelta(hours=1))

    return jsonify({
        "taskId": task_id,
        "status": "started",
        "estimatedTime": 300,
        "wsToken": ws_token,
        "wsChannel": ws_channel,
    }), 202


@bp.get("/wifi/audit/result/<task_id>")
@require_audit_auth
def get_wifi_audit_result(task_id):
    result = models.WifiAuditResult.query.filter_by(task_id=task_id).first()
    if not result:
        return jsonify({"error": "Task not found"}), 404

    details = result.details or {}
    return jsonify({
        "bssid": result.bssid,
        "essid": result.essid,
        "isVulnerable": bool(result.is_vulnerable),
        "vulnerabilityType": result.vulnerability_type,
        "foundPassword": result.found_password,
        "message": details.get("message", ""),
        "status": details.get("status", "completed"),
        "progress": int(result.progress or details.get("progress", 0)),
        "estimatedTime": int(result.estimated_time_seconds or details.get("estimatedTime", 0)),
    })


@bp.get("/wifi/audit/status/<task_id>")
@require_audit_auth
def get_wifi_audit_status(task_id):
    result = models.WifiAuditResult.query.filter_by(task_id=task_id).first()
    if not result:
        return jsonify({"error": "Task not found"}), 404

    details = result.details or {}
    status = details.get("status", "pending")
    return jsonify({
        "taskId": result.task_id,
        "status": status,
        "progress": int(result.progress or details.get("progress", 0)),
        "estimatedTime": int(result.estimated_time_seconds or details.get("estimatedTime", 0)),
        "isVulnerable": bool(result.is_vulnerable),
        "vulnerabilityType": result.vulnerability_type,
        "foundPassword": result.found_password,
        "message": details.get("message", ""),
    })


@bp.get("/osint/cameras")
@jwt_or_api_required
def list_global_cameras():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    country = request.args.get('country')
    vendor = request.args.get('vendor')

    query = models.GlobalCamera.query
    if country:
        query = query.filter_by(country=country)
    if vendor:
        query = query.filter_by(vendor=vendor)

    cameras = query.paginate(page=page, per_page=per_page)
    return jsonify({
        'items': [{
            'ip': c.ip,
            'port': c.port,
            'vendor': c.vendor,
            'model': c.model,
            'country': c.country,
            'city': c.city,
            'org': c.org,
        } for c in cameras.items],
        'total': cameras.total,
        'page': page,
    })
