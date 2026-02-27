import json

import pytest

from app.services.geocode_service import geocode


def test_geocode_offline(monkeypatch, app, tmp_path):
    """Если в офлайн-базе есть совпадение, онлайн-сервис не вызывается."""
    offline_data = [
        {"name": "Some place", "display_name": "Some place full", "lat": "1.23", "lon": "4.56"},
        {"name": "Other", "display_name": "Other place", "lat": "7.89", "lon": "0.12"},
    ]
    offline_file = tmp_path / "geocode.json"
    offline_file.write_text(json.dumps(offline_data), encoding="utf-8")

    # Подменяем конфиг приложения
    app.config["OFFLINE_GEOCODE_FILE"] = str(offline_file)

    # Подменяем requests.get, чтобы гарантированно не вызывался
    def fake_get(*args, **kwargs):  # pragma: no cover - защита от вызова
        raise AssertionError("requests.get should not be called when offline hit exists")

    monkeypatch.setattr("app.services.geocode_service.requests.get", fake_get)

    with app.app_context():
        results = geocode("some", limit=1, lang="ru")

    assert len(results) == 1
    assert results[0]["display_name"] == "Some place full"


def test_geocode_online_fallback(monkeypatch, app):
    """Если офлайн-совпадений нет, должен использоваться онлайн‑сервис."""
    app.config["OFFLINE_GEOCODE_FILE"] = None

    class DummyResponse:
        def __init__(self, ok, payload):
            self.ok = ok
            self._payload = payload

        def json(self):
            return self._payload

    def fake_get(url, params=None, headers=None, timeout=10):
        assert "nominatim" in url
        return DummyResponse(True, [
            {"display_name": "Online place", "lat": "11.11", "lon": "22.22"},
        ])

    monkeypatch.setattr("app.services.geocode_service.requests.get", fake_get)

    with app.app_context():
        results = geocode("online", limit=1, lang="ru")

    assert len(results) == 1
    assert results[0]["display_name"] == "Online place"
