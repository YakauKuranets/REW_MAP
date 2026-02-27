from datetime import datetime

from app.extensions import db


class Wordlist(db.Model):
    """Модель для хранения информации о загруженных словарях."""

    __tablename__ = "wordlists"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    version = db.Column(db.Integer, default=1)
    size = db.Column(db.Integer)
    file_path = db.Column(db.String(255))
    source_url = db.Column(db.String(500))
    hash = db.Column(db.String(64))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)

    def __repr__(self):
        return f"<Wordlist {self.name} v{self.version}>"
