import hashlib
import hmac
import json
from urllib.parse import urlencode

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


def test_webapp_submit_rejects_invalid_init_data(client, app):
    app.config["TELEGRAM_BOT_TOKEN"] = "bot-secret"

    rv = client.post(
        "/api/bot/webapp_submit",
        json={"category": "Охрана", "description": "test", "coords": {"lat": 53.9, "lon": 27.56}, "initData": "hash=fake"},
    )
    assert rv.status_code == 403


def test_webapp_submit_creates_pending_with_valid_init_data(client, app):
    token = "bot-secret"
    app.config["TELEGRAM_BOT_TOKEN"] = token
    init_data = _build_init_data(token, {"id": 12345, "username": "miniuser", "last_name": "Иванов"})

    rv = client.post(
        "/api/bot/webapp_submit",
        json={
            "category": "Охрана",
            "description": "Описание из мини-аппа",
            "coords": {"lat": 53.9, "lon": 27.56},
            "photo": "https://cdn.example/img.jpg",
            "initData": init_data,
        },
    )
    assert rv.status_code == 200

    pending = PendingMarker.query.order_by(PendingMarker.id.desc()).first()
    assert pending is not None
    assert pending.category == "Охрана"
    assert pending.reporter == "Иванов"
