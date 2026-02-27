from __future__ import annotations

from flask import jsonify, request

from app.auth.decorators import jwt_or_api_required
from app.extensions import db

from . import bp
from .models import AlertHistory, AlertRule


@bp.get("/rules")
@jwt_or_api_required
def list_rules():
    rules = AlertRule.query.order_by(AlertRule.id.asc()).all()
    return jsonify([r.to_dict() for r in rules])


@bp.post("/rules")
@jwt_or_api_required
def create_rule():
    data = request.get_json(silent=True) or {}
    rule = AlertRule(
        name=(data.get("name") or "").strip() or "Security alert rule",
        condition=(data.get("condition") or "cvss_gt").strip(),
        threshold=data.get("threshold"),
        channel=(data.get("channel") or "websocket").strip(),
        enabled=bool(data.get("enabled", True)),
    )
    db.session.add(rule)
    db.session.commit()
    return jsonify(rule.to_dict()), 201


@bp.patch("/rules/<int:rule_id>")
@jwt_or_api_required
def patch_rule(rule_id: int):
    rule = AlertRule.query.get_or_404(rule_id)
    data = request.get_json(silent=True) or {}

    if "name" in data:
        rule.name = (data.get("name") or "").strip() or rule.name
    if "condition" in data:
        rule.condition = (data.get("condition") or "").strip() or rule.condition
    if "threshold" in data:
        rule.threshold = data.get("threshold")
    if "channel" in data:
        rule.channel = (data.get("channel") or "").strip() or rule.channel
    if "enabled" in data:
        rule.enabled = bool(data.get("enabled"))

    db.session.add(rule)
    db.session.commit()
    return jsonify(rule.to_dict())


@bp.delete("/rules/<int:rule_id>")
@jwt_or_api_required
def delete_rule(rule_id: int):
    rule = AlertRule.query.get_or_404(rule_id)
    db.session.delete(rule)
    db.session.commit()
    return ("", 204)


@bp.get("/history")
@jwt_or_api_required
def list_history():
    limit = min(max(int(request.args.get("limit", 100)), 1), 500)
    rows = AlertHistory.query.order_by(AlertHistory.created_at.desc()).limit(limit).all()
    return jsonify([row.to_dict() for row in rows])
