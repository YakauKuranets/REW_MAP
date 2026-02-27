from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from flask import jsonify, request, session

from . import bp
from ..extensions import db
from ..helpers import require_admin
from ..models import ServiceAccess
from ..security.api_keys import require_bot_api_key


VALID_STATUSES = {"guest", "pending", "officer", "admin", "denied"}


def _now() -> datetime:
    return datetime.utcnow()


def _get_tg_user_id_from_request() -> str:
    """Extract Telegram user id from request.

    Priority:
    - JSON body: tg_user_id
    - query param: tg_user_id
    - header: X-Telegram-Id
    """
    uid = ""
    try:
        if request.is_json:
            payload = request.get_json(silent=True) or {}
            uid = str(payload.get("tg_user_id") or "").strip()
    except Exception:
        uid = ""

    if not uid:
        uid = str(request.args.get("tg_user_id") or "").strip()

    if not uid:
        uid = str(request.headers.get("X-Telegram-Id") or "").strip()

    return uid[:64]


def _get_or_create(uid: str) -> ServiceAccess:
    row = ServiceAccess.query.filter_by(tg_user_id=str(uid)).first()
    if row:
        return row
    row = ServiceAccess(tg_user_id=str(uid), status="guest", updated_at=_now())
    db.session.add(row)
    db.session.flush()
    return row


@bp.post("/access/request")
def service_access_request():
    """Create/update request for service access.

    Client: Telegram bot.
    Auth: BOT_API_KEY (X-API-KEY).

    Body JSON:
      {"tg_user_id": "...", "note": "..."}

    Result:
      {"tg_user_id": "...", "status": "pending"|"officer"|"admin"|...}
    """
    require_bot_api_key(allow_query_param=False)

    uid = _get_tg_user_id_from_request()
    if not uid:
        return jsonify({"error": "missing_tg_user_id"}), 400

    note = ""
    try:
        payload = request.get_json(silent=True) or {}
        note = str(payload.get("note") or "").strip()[:256]
    except Exception:
        note = ""

    row = _get_or_create(uid)
    cur = row.normalize_status()

    # If already has access, keep it
    if cur in {"officer", "admin"}:
        row.updated_at = _now()
        if note:
            row.note = note
        db.session.commit()
        return jsonify({"tg_user_id": row.tg_user_id, "status": row.normalize_status()}), 200

    # Otherwise set pending
    row.status = "pending"
    row.requested_at = _now()
    row.decided_at = None
    row.decided_by = None
    row.updated_at = _now()
    if note:
        row.note = note

    db.session.commit()
    return jsonify({"tg_user_id": row.tg_user_id, "status": row.normalize_status()}), 200


@bp.get("/access/status")
def service_access_status():
    """Get current service access status for Telegram user.

    Client: Telegram bot.
    Auth: BOT_API_KEY (X-API-KEY).

    Query: ?tg_user_id=...
    """
    require_bot_api_key(allow_query_param=False)

    uid = _get_tg_user_id_from_request()
    if not uid:
        return jsonify({"error": "missing_tg_user_id"}), 400

    row = ServiceAccess.query.filter_by(tg_user_id=str(uid)).first()
    if not row:
        return jsonify({"tg_user_id": uid, "status": "guest"}), 200

    return jsonify({"tg_user_id": row.tg_user_id, "status": row.normalize_status()}), 200


# -------------------------
# Admin endpoints (web session)
# -------------------------


def _admin_actor() -> str:
    return str(session.get("admin_username") or session.get("username") or "admin").strip()[:128] or "admin"


@bp.get("/access/admin/pending")
def admin_list_pending():
    """List pending service access requests."""
    require_admin(min_role="editor")
    rows = ServiceAccess.query.filter(ServiceAccess.status == "pending").order_by(ServiceAccess.requested_at.desc().nullslast()).all()
    return jsonify({"items": [r.to_dict() for r in rows]}), 200


@bp.get("/access/admin/pending_count")
def admin_pending_count():
    """Count pending service access requests (lightweight for Command Center badge)."""
    require_admin(min_role="editor")
    cnt = ServiceAccess.query.filter(ServiceAccess.status == "pending").count()
    return jsonify({"count": int(cnt)}), 200


@bp.get("/access/admin/users")
def admin_list_users():
    """List all service access rows."""
    require_admin(min_role="editor")
    rows = ServiceAccess.query.order_by(ServiceAccess.updated_at.desc().nullslast()).all()
    return jsonify({"items": [r.to_dict() for r in rows]}), 200


def _admin_set_status(uid: str, new_status: str, note: str = "") -> ServiceAccess:
    row = _get_or_create(uid)
    if new_status not in VALID_STATUSES:
        new_status = "guest"

    row.status = new_status
    row.decided_at = _now()
    row.decided_by = _admin_actor()
    row.updated_at = _now()
    if note:
        row.note = note[:256]
    db.session.commit()
    return row


@bp.post("/access/admin/approve")
def admin_approve():
    require_admin(min_role="editor")
    payload: Dict[str, Any] = request.get_json(silent=True) or {}
    uid = str(payload.get("tg_user_id") or "").strip()[:64]
    if not uid:
        return jsonify({"error": "missing_tg_user_id"}), 400
    note = str(payload.get("note") or "").strip()[:256]
    row = _admin_set_status(uid, "officer", note=note)
    # best-effort notify user in Telegram (optional)
    try:
        from flask import current_app
        from ..integrations.telegram_sender import send_telegram_message
        bot_token = (current_app.config.get("TELEGRAM_BOT_TOKEN") or "").strip()
        if bot_token:
            send_telegram_message(
                bot_token,
                uid,
                "✅ Доступ к разделу «Служба» одобрен. Теперь в боте появится кнопка «Служба».",
            )
    except Exception:
        pass
    return jsonify(row.to_dict()), 200


@bp.post("/access/admin/deny")
def admin_deny():
    require_admin(min_role="editor")
    payload: Dict[str, Any] = request.get_json(silent=True) or {}
    uid = str(payload.get("tg_user_id") or "").strip()[:64]
    if not uid:
        return jsonify({"error": "missing_tg_user_id"}), 400
    note = str(payload.get("note") or "").strip()[:256]
    row = _admin_set_status(uid, "denied", note=note)
    return jsonify(row.to_dict()), 200


@bp.post("/access/admin/revoke")
def admin_revoke():
    require_admin(min_role="editor")
    payload: Dict[str, Any] = request.get_json(silent=True) or {}
    uid = str(payload.get("tg_user_id") or "").strip()[:64]
    if not uid:
        return jsonify({"error": "missing_tg_user_id"}), 400
    note = str(payload.get("note") or "").strip()[:256]
    row = _admin_set_status(uid, "guest", note=note)
    return jsonify(row.to_dict()), 200
