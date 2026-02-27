from app.extensions import db
from datetime import datetime

class CameraAuditResult(db.Model):
    __tablename__ = 'camera_audit_results'
    id = db.Column(db.Integer, primary_key=True)
    target_ip = db.Column(db.String(45), nullable=False, index=True)
    target_port = db.Column(db.Integer, default=80)
    vendor = db.Column(db.String(100))
    model = db.Column(db.String(100))
    username = db.Column(db.String(50))
    password_found = db.Column(db.String(255))
    method = db.Column(db.String(50))  # 'vuln', 'bruteforce', 'none'
    success = db.Column(db.Boolean, default=False)
    details = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)


class WifiAuditResult(db.Model):
    __tablename__ = 'wifi_audit_results'
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.String(36), unique=True, nullable=False)
    client_id = db.Column(db.String(100))
    bssid = db.Column(db.String(17))
    essid = db.Column(db.String(100))
    security_type = db.Column(db.String(32))
    is_vulnerable = db.Column(db.Boolean, default=False)
    vulnerability_type = db.Column(db.String(50))
    found_password = db.Column(db.String(100))
    estimated_time_seconds = db.Column(db.Integer, default=0)
    progress = db.Column(db.Integer, default=0)
    details = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)


class HandshakeAnalysis(db.Model):
    __tablename__ = 'handshake_analyses'

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.String(36), unique=True, nullable=False)
    client_id = db.Column(db.String(100))
    bssid = db.Column(db.String(17))
    essid = db.Column(db.String(100))
    security_type = db.Column(db.String(32))
    handshake_file = db.Column(db.String(255))
    status = db.Column(db.String(20), default='pending')
    progress = db.Column(db.Integer, default=0)
    password_found = db.Column(db.String(100))
    attack_type = db.Column(db.String(20), default='handshake')
    estimated_time = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)


class GlobalCamera(db.Model):
    __tablename__ = 'global_cameras'

    id = db.Column(db.Integer, primary_key=True)
    ip = db.Column(db.String(45), nullable=False, index=True)
    port = db.Column(db.Integer, default=80)
    vendor = db.Column(db.String(100))
    model = db.Column(db.String(100))
    country = db.Column(db.String(100))
    city = db.Column(db.String(100))
    org = db.Column(db.String(200))
    hostnames = db.Column(db.JSON)
    vulnerabilities = db.Column(db.JSON)
    first_seen = db.Column(db.DateTime, default=datetime.utcnow)
    last_seen = db.Column(db.DateTime, onupdate=datetime.utcnow)
    is_analyzed = db.Column(db.Boolean, default=False)
