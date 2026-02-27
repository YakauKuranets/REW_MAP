import hashlib
import hmac
import json
from urllib.parse import urlencode

from app import create_app
from app.config import TestingConfig
from app.models import PendingMarker


def _build_init_data(bot_token: str, user: dict) -> str:
    data = {
        "auth_date": "1700000000",
        "query_id": "AAEAAAE",
        "user": json.dumps(user, separators=(",", ":"), ensure_ascii=False),
    }
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(data.items(), key=lambda kv: kv[0]))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    sig = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    data["hash"] = sig
    return urlencode(data)


def test_ai_vision_updates_pending_and_broadcasts_incident_updated(monkeypatch, tmp_path):
    db_path = tmp_path / "ai_vision.db"
    monkeypatch.setenv("DATABASE_URI", f"sqlite:///{db_path}")

    app = create_app(TestingConfig)
    app.config["TELEGRAM_BOT_TOKEN"] = "bot-secret"

    image_path = tmp_path / "burning_car_fire.jpg"
    image_path.write_bytes(b"fake-image")

    monkeypatch.setattr(
        "app.bot.routes.analyze_incident_photo",
        lambda _path: {"tags": ["fire", "car"], "priority": 5, "category": "fire"},
    )

    events = []
    monkeypatch.setattr("app.bot.routes.broadcast_event_sync", lambda event, payload: events.append((event, payload)))

    class ImmediateThread:
        def __init__(self, target=None, args=(), daemon=None):
            self._target = target
            self._args = args

        def start(self):
            self._target(*self._args)

    monkeypatch.setattr("app.bot.routes.Thread", ImmediateThread)

    init_data = _build_init_data("bot-secret", {"id": 12345, "username": "miniuser", "last_name": "Иванов"})

    with app.app_context():
        client = app.test_client()
        rv = client.post(
            "/api/bot/webapp_submit",
            json={
                "category": "Охрана",
                "description": "Описание из мини-аппа",
                "coords": {"lat": 53.9, "lon": 27.56},
                "photo": str(image_path),
                "initData": init_data,
            },
        )
        assert rv.status_code == 200

        pending = PendingMarker.query.order_by(PendingMarker.id.desc()).first()
        assert pending is not None
        assert pending.ai_tags == ["fire", "car"]
        assert pending.priority == 5

    names = [e[0] for e in events]
    assert "pending_created" in names
    assert "incident_updated" in names
