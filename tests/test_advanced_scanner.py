from __future__ import annotations

from flask import Flask

from app.osint.advanced_scanner import AdvancedOSINTScanner


class _Resp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def test_search_by_cve(monkeypatch):
    app = Flask(__name__)
    app.config.update(SHODAN_API_KEY="k", CENSYS_API_ID="id", CENSYS_SECRET="sec")

    with app.app_context():
        scanner = AdvancedOSINTScanner()

    def fake_get(url, params=None, auth=None, timeout=0):
        if "shodan" in url:
            return _Resp(200, {"matches": [{"ip_str": "1.1.1.1", "port": 443, "location": {"country_name": "DE", "city": "Berlin"}, "org": "Org"}]})
        return _Resp(200, {"result": {"first_seen": "a", "last_seen": "b", "services": [{"port": 443, "tls": {"version": "TLSv1.3", "cipher_suites": ["X"]}}]}})

    monkeypatch.setattr(scanner.session, "get", fake_get)
    rows = scanner.search_by_cve("CVE-1", country="DE")
    hist = scanner.get_device_history("1.1.1.1")
    assert rows and rows[0]["source"] == "shodan"
    assert hist["tls_configs"][0]["version"] == "TLSv1.3"
