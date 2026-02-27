from __future__ import annotations


def test_bot_markers_requires_api_key_when_configured(client, app):
    """/api/bot/* разрешён только при правильном BOT_API_KEY (если задан)."""
    app.config["BOT_API_KEY"] = "k"

    payload = {"name": "Test marker", "lat": 53.9, "lon": 27.56}

    r = client.post("/api/bot/markers", json=payload)
    assert r.status_code == 403

    r = client.post("/api/bot/markers", json=payload, headers={"X-API-KEY": "k"})
    assert r.status_code == 200
    j = r.get_json() or {}
    assert "pending" in j


def test_duty_bot_requires_header_key(client, app):
    """Duty bot endpoints требуют ключ в заголовке (query param не принимаем)."""
    app.config["BOT_API_KEY"] = "k"

    payload = {"user_id": "123", "lat": 53.9, "lon": 27.56}

    r = client.post("/api/duty/bot/checkin", json=payload)
    assert r.status_code == 403

    r = client.post("/api/duty/bot/checkin", json=payload, headers={"X-API-KEY": "k"})
    assert r.status_code == 200

    # query param api_key не должен работать для duty
    r = client.post("/api/duty/bot/checkin?api_key=k", json=payload)
    assert r.status_code == 403
