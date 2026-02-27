from __future__ import annotations

from compat_flask import jsonify, request, current_app

from . import bp
from ..helpers import require_admin
from .retention import get_retention_config, run_retention_cleanup, get_last_retention_status


@bp.get("/retention/preview")
def retention_preview():
    """Show current retention configuration and computed defaults."""
    require_admin("superadmin")
    cfg = current_app.config
    return jsonify({
        "RETENTION_TRACK_DAYS": int(cfg.get("RETENTION_TRACK_DAYS", 30)),
        "RETENTION_CHAT_DAYS": int(cfg.get("RETENTION_CHAT_DAYS", 90)),
        "RETENTION_INCIDENTS_DAYS": int(cfg.get("RETENTION_INCIDENTS_DAYS", 180)),
        "RETENTION_DELETE_ONLY_CLOSED": bool(cfg.get("RETENTION_DELETE_ONLY_CLOSED", True)),
        "RETENTION_RUN_ON_STARTUP": bool(cfg.get("RETENTION_RUN_ON_STARTUP", False)),
        "computed": get_retention_config(),
    })


@bp.post("/retention/run")
def retention_run():
    """Run retention cleanup now (admin-only).

    JSON body (optional): {"dry_run": true}
    """
    require_admin("superadmin")
    body = request.get_json(silent=True) or {}
    dry_run = bool(body.get("dry_run", False))

    report = run_retention_cleanup(dry_run=dry_run)
    return jsonify(report), 200


@bp.get("/retention/last")
def retention_last():
    """Return last retention scheduler/manual run status (best-effort)."""
    require_admin("superadmin")
    return jsonify(get_last_retention_status()), 200


@bp.get("/retention/scheduler")
def retention_scheduler_status():
    """Expose scheduler configuration knobs for ops visibility."""
    require_admin("superadmin")
    cfg = current_app.config
    return jsonify({
        "enabled": bool(cfg.get("RETENTION_SCHEDULER_ENABLED", False)),
        "every_minutes": int(cfg.get("RETENTION_SCHEDULER_EVERY_MINUTES", 360)),
        "start_delay_sec": int(cfg.get("RETENTION_SCHEDULER_START_DELAY_SEC", 30)),
        "lock_key": str(cfg.get("RETENTION_SCHEDULER_LOCK_KEY", "mapv12:retention:lock")),
        "lock_ttl_sec": int(cfg.get("RETENTION_SCHEDULER_LOCK_TTL_SEC", 600)),
        "redis_url_configured": bool(str(cfg.get("REDIS_URL") or "").strip()),
    }), 200
