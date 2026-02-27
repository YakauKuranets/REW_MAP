from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db


class DiagnosticTarget(db.Model):
    __tablename__ = "diagnostic_targets"

    id = db.Column(db.Integer, primary_key=True)
    target_type = db.Column("type", db.String(32), nullable=False, index=True)
    identifier = db.Column(db.String(255), nullable=False, index=True)
    status = db.Column(db.String(32), nullable=False, default="pending", index=True)
    context = db.Column(db.JSON, nullable=True)
    result = db.Column(db.JSON, nullable=True)
    risk_summary = db.Column(db.Text, nullable=True)
    recommendations = db.Column(db.JSON, nullable=True)
    nonconformities = db.Column(db.JSON, nullable=True)
    feedback = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    @property
    def type(self) -> str:  # compatibility with earlier coordinator snippets
        return self.target_type

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.target_type,
            "identifier": self.identifier,
            "status": self.status,
            "context": self.context or {},
            "result": self.result or {},
            "riskSummary": self.risk_summary,
            "recommendations": self.recommendations or [],
            "nonconformities": self.nonconformities or [],
            "feedback": self.feedback or {},
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
        }


class DiagnosticsAgent(db.Model):
    __tablename__ = "diagnostics_agents"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    platform = db.Column(db.String(64), nullable=True)
    status = db.Column(db.String(32), nullable=False, default="offline", index=True)
    details = db.Column(db.JSON, nullable=True)
    last_seen_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "platform": self.platform,
            "status": self.status,
            "metadata": self.details or {},
            "lastSeenAt": self.last_seen_at.isoformat() if self.last_seen_at else None,
        }


class AlertSubscription(db.Model):
    __tablename__ = "alert_subscriptions"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False, index=True)
    min_severity = db.Column(db.Integer, default=7, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "email": self.email,
            "min_severity": int(self.min_severity or 0),
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "isActive": bool(self.is_active),
        }
