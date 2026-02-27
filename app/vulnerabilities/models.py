from __future__ import annotations

from datetime import datetime

from app.extensions import db


class CVE(db.Model):
    __tablename__ = "cves"

    id = db.Column(db.String(20), primary_key=True)  # CVE-2024-12345
    description = db.Column(db.Text)
    cvss_score = db.Column(db.Float)
    exploit_available = db.Column(db.Boolean, default=False)
    affected_products = db.Column(db.JSON)  # [{vendor, product, version}]
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<CVE {self.id} cvss={self.cvss_score}>"
