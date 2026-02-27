from __future__ import annotations

import app.tasks.diagnostics_scans as scans


class _FakeTarget:
    def __init__(self, id_=1):
        self.id = id_
        self.result = {}
        self.status = "pending"


class _FakeQuery:
    def __init__(self, target):
        self._target = target

    def get(self, _id):
        return self._target


class _FakeSession:
    def __init__(self):
        self.added = []
        self.commits = 0

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.commits += 1


def test_run_profinet_scan(monkeypatch):
    target = _FakeTarget(42)
    monkeypatch.setattr(scans.DiagnosticTarget, "query", _FakeQuery(target))

    class FakeAnalyzer:
        def __init__(self, interface="eth0"):
            self.interface = interface

        def discover_devices(self):
            return [{"mac": "aa:bb", "ip": "1.1.1.1"}]

    fake_session = _FakeSession()
    monkeypatch.setattr(scans.db, "session", fake_session)

    import app.diagnostics.industrial.profinet_analyzer as pn

    monkeypatch.setattr(pn, "ProfinetAnalyzer", FakeAnalyzer)

    out = scans.run_profinet_scan(target_id=42, interface="eth1")
    assert out["ok"] is True
    assert target.status == "completed"
    assert target.result["count"] == 1
    assert fake_session.commits == 1


def test_run_mqtt_scan(monkeypatch):
    target = _FakeTarget(7)
    monkeypatch.setattr(scans.DiagnosticTarget, "query", _FakeQuery(target))

    class FakeMQTT:
        def check(self, host, port=1883):
            return {"host": host, "port": port, "reachable": True}

    fake_session = _FakeSession()
    monkeypatch.setattr(scans.db, "session", fake_session)

    import app.diagnostics.industrial.mqtt_broker_check as mqtt_mod

    monkeypatch.setattr(mqtt_mod, "MQTTBrokerCheck", FakeMQTT)

    out = scans.run_mqtt_scan(target_id=7, ip="10.0.0.5", port=1884)
    assert out["ok"] is True
    assert target.result["reachable"] is True
    assert target.status == "completed"
