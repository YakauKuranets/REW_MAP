from __future__ import annotations

import sys
import types

# Optional dependency in video security audit chain may be absent in CI/test env.
sys.modules.setdefault("aiohttp_digest_auth", types.SimpleNamespace(DigestAuth=object))

import app.tasks.shodan_scanner as scanner


class _FakeSession:
    def __init__(self):
        self.added = []
        self.commits = 0
        self.rollbacks = 0

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class _FakeCameraQuery:
    def filter_by(self, **kwargs):
        return self

    def first(self):
        return None


class _FakeCamera:
    query = _FakeCameraQuery()

    def __init__(self, **kwargs):
        self.data = kwargs


class _FakeApi:
    def search(self, query, limit=100):
        return {
            "total": 1,
            "matches": [
                {
                    "ip_str": "1.2.3.4",
                    "port": 80,
                    "product": "Hikvision",
                    "info": "cam",
                    "location": {"country_name": "X", "city": "Y"},
                    "org": "Org",
                    "hostnames": ["h"],
                    "vulns": ["CVE-1"],
                }
            ],
        }


def test_scan_shodan_for_cameras_use_tor(monkeypatch):
    fake_db_session = _FakeSession()
    monkeypatch.setattr(scanner.db, "session", fake_db_session)
    monkeypatch.setattr(scanner, "_global_camera_model", lambda: _FakeCamera)
    monkeypatch.setattr(scanner, "SHODAN_API_KEY", "ok")

    created = {"tor": 0, "renew": 0, "close": 0, "tor_session_used": False}

    class FakeTor:
        def __init__(self):
            created["tor"] += 1
            self.session = object()

        def get_current_ip(self):
            return "9.9.9.9"

        def renew_identity(self):
            created["renew"] += 1
            return True

        def close(self):
            created["close"] += 1

    fake_module = types.ModuleType("app.network.tor_client")
    fake_module.TorProxyClient = FakeTor

    import sys

    monkeypatch.setitem(sys.modules, "app.network.tor_client", fake_module)

    def fake_build_client(api_key, tor_session=None):
        if tor_session is not None:
            created["tor_session_used"] = True
        return _FakeApi()

    monkeypatch.setattr(scanner, "_build_shodan_client", fake_build_client)

    result = scanner.scan_shodan_for_cameras(query='product:"Hikvision"', limit=10, use_tor=True)
    assert "Найдено 1 устройств" in result
    assert created == {"tor": 1, "renew": 1, "close": 1, "tor_session_used": True}
    assert fake_db_session.commits == 1


def test_build_shodan_client_with_fallback(monkeypatch):
    calls = []

    class FakeShodanCtor:
        def __call__(self, *args, **kwargs):
            calls.append((args, kwargs))
            if kwargs:
                raise TypeError("unexpected kwargs")
            return "client"

    monkeypatch.setattr(scanner.shodan, "Shodan", FakeShodanCtor())
    out = scanner._build_shodan_client("k", tor_session=object())
    assert out == "client"
    assert len(calls) == 2
