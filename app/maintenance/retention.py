from __future__ import annotations

"""Retention / cleanup helpers.

Best-effort implementation that can be triggered manually via admin API.

Safety defaults:
- Incidents are deleted only when status is resolved/closed (configurable)
- Media files are NOT deleted automatically (only DB rows)

We intentionally avoid new dependencies.
"""

import time
from datetime import datetime, timedelta
from typing import Any, Dict, List

from flask import current_app

from ..extensions import db
from ..models import (
    TrackingPoint,
    TrackingStop,
    Incident,
    IncidentEvent,
    IncidentAssignment,
)

try:
    # Optional: chat2 models may be absent in older bundles
    from ..event_chat.models import Message as Chat2Message
except Exception:  # pragma: no cover
    Chat2Message = None  # type: ignore


# --- Last run status (in-memory, best-effort) ---
# This is helpful for ops visibility. It's per-process.
_LAST_STATUS: Dict[str, Any] = {
    "kind": "never",
    "ts": None,
}


def set_last_retention_status(status: Dict[str, Any]) -> None:
    """Store last retention status (best-effort, in-memory)."""
    global _LAST_STATUS
    try:
        _LAST_STATUS = dict(status or {})
    except Exception:
        _LAST_STATUS = {"kind": "error", "ts": None}


def get_last_retention_status() -> Dict[str, Any]:
    """Return last retention status (best-effort, in-memory)."""
    try:
        return dict(_LAST_STATUS)
    except Exception:
        return {"kind": "error", "ts": None}


def _utcnow() -> datetime:
    return datetime.utcnow()


def get_retention_config() -> Dict[str, Any]:
    cfg = current_app.config
    return {
        "tracks_days": int(cfg.get("RETENTION_TRACK_DAYS", 30)),
        "chat_days": int(cfg.get("RETENTION_CHAT_DAYS", 90)),
        "incidents_days": int(cfg.get("RETENTION_INCIDENTS_DAYS", 180)),
        "delete_only_closed": bool(cfg.get("RETENTION_DELETE_ONLY_CLOSED", True)),
    }


def run_retention_cleanup(*, dry_run: bool = False) -> Dict[str, Any]:
    """Run retention cleanup.

    Returns a JSON-serializable report.

    IMPORTANT: For safety we do NOT delete media files on disk here.
    """
    t0 = time.time()
    cfg = get_retention_config()

    now = _utcnow()
    cutoff_track_dt = now - timedelta(days=cfg["tracks_days"])
    cutoff_chat_dt = now - timedelta(days=cfg["chat_days"])
    cutoff_inc_dt = now - timedelta(days=cfg["incidents_days"])

    # TrackingPoint.ts is epoch milliseconds
    cutoff_track_ts = int(cutoff_track_dt.timestamp() * 1000)

    report: Dict[str, Any] = {
        "dry_run": dry_run,
        "now_utc": now.isoformat() + "Z",
        "cutoffs": {
            "tracks_ts_ms": cutoff_track_ts,
            "chat_created_at": cutoff_chat_dt.isoformat() + "Z",
            "incidents_updated_at": cutoff_inc_dt.isoformat() + "Z",
        },
        "deleted": {
            "tracking_points": 0,
            "tracking_stops": 0,
            "chat2_messages": 0,
            "incident_events": 0,
            "incident_assignments": 0,
            "incidents": 0,
        },
    }

    # --- Tracks ---
    q_points = db.session.query(TrackingPoint).filter(TrackingPoint.ts < cutoff_track_ts)
    q_stops = db.session.query(TrackingStop).filter(
        (TrackingStop.end_ts.isnot(None) & (TrackingStop.end_ts < cutoff_track_ts))
        | (TrackingStop.end_ts.is_(None) & (TrackingStop.start_ts < cutoff_track_ts))
    )

    if dry_run:
        report["deleted"]["tracking_points"] = int(q_points.count())
        report["deleted"]["tracking_stops"] = int(q_stops.count())
    else:
        report["deleted"]["tracking_points"] = int(q_points.delete(synchronize_session=False))
        report["deleted"]["tracking_stops"] = int(q_stops.delete(synchronize_session=False))

    # --- Chat2 ---
    if Chat2Message is not None:
        q_chat2 = db.session.query(Chat2Message).filter(Chat2Message.created_at < cutoff_chat_dt)
        if dry_run:
            report["deleted"]["chat2_messages"] = int(q_chat2.count())
        else:
            report["deleted"]["chat2_messages"] = int(q_chat2.delete(synchronize_session=False))

    # --- Incidents ---
    q_inc = db.session.query(Incident).filter(Incident.updated_at < cutoff_inc_dt)
    if cfg["delete_only_closed"]:
        q_inc = q_inc.filter(Incident.status.in_(["resolved", "closed"]))

    incident_ids: List[str] = [row[0] for row in q_inc.with_entities(Incident.id).all()]

    if dry_run:
        report["deleted"]["incidents"] = len(incident_ids)
        if incident_ids:
            report["deleted"]["incident_events"] = int(
                db.session.query(IncidentEvent).filter(IncidentEvent.incident_id.in_(incident_ids)).count()
            )
            report["deleted"]["incident_assignments"] = int(
                db.session.query(IncidentAssignment).filter(IncidentAssignment.incident_id.in_(incident_ids)).count()
            )
    else:
        if incident_ids:
            report["deleted"]["incident_events"] = int(
                db.session.query(IncidentEvent).filter(IncidentEvent.incident_id.in_(incident_ids)).delete(synchronize_session=False)
            )
            report["deleted"]["incident_assignments"] = int(
                db.session.query(IncidentAssignment).filter(IncidentAssignment.incident_id.in_(incident_ids)).delete(synchronize_session=False)
            )
            report["deleted"]["incidents"] = int(
                db.session.query(Incident).filter(Incident.id.in_(incident_ids)).delete(synchronize_session=False)
            )

    if not dry_run:
        db.session.commit()

    report["duration_sec"] = round(time.time() - t0, 4)

    # Save last status for ops visibility (in-memory).
    try:
        set_last_retention_status({
            "kind": "dry_run" if dry_run else "run",
            "ts": int(time.time()),
            "report": report,
        })
    except Exception:
        pass
    return report
