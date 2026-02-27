from __future__ import annotations

from datetime import datetime

from app.extensions import db


class AlertRule(db.Model):
    __tablename__ = "alert_rules"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    condition = db.Column(db.String(50), nullable=False, index=True)
    threshold = db.Column(db.Float, nullable=True)
    channel = db.Column(db.String(50), nullable=False, default="websocket")
    enabled = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "condition": self.condition,
            "threshold": self.threshold,
            "channel": self.channel,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AlertHistory(db.Model):
    __tablename__ = "alert_history"

    id = db.Column(db.Integer, primary_key=True)
    rule_id = db.Column(db.Integer, db.ForeignKey("alert_rules.id"), nullable=False, index=True)
    message = db.Column(db.Text, nullable=False)
    severity = db.Column(db.String(20), nullable=False, default="high")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    rule = db.relationship("AlertRule", backref=db.backref("history", lazy="dynamic"))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "rule_id": self.rule_id,
            "message": self.message,
            "severity": self.severity,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
