from __future__ import annotations

import io
import json
import zipfile

import app.tasks.cve_updater as updater


class _FakeRecord:
    def __init__(self, id_):
        self.id = id_
        self.description = ""
        self.cvss_score = None
        self.affected_products = []
        self.last_updated = None


class _FakeQuery:
    def get(self, _id):
        return None


def _zip_payload(payload: dict) -> bytes:
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("feed.json", json.dumps(payload).encode("utf-8"))
    return bio.getvalue()


def test_update_nvd_cve_triggers_alert(monkeypatch):
    payload = {
        "CVE_Items": [
            {
                "cve": {
                    "CVE_data_meta": {"ID": "CVE-TEST-1"},
                    "description": {"description_data": [{"value": "critical issue"}]},
                },
                "impact": {"baseMetricV3": {"cvssV3": {"baseScore": 9.8}}},
                "configurations": {"nodes": [{"cpe_match": [{"cpe23Uri": "cpe:2.3:a:acme:cam:1.0:*:*:*:*:*:*:*"}]}]},
            }
        ]
    }

    class FakeResp:
        content = _zip_payload(payload)

        def raise_for_status(self):
            return None

    monkeypatch.setattr(updater.requests, "get", lambda *a, **k: FakeResp())
    monkeypatch.setattr(updater.CVE, "query", _FakeQuery())
    monkeypatch.setattr(updater, "CVE", type("CVECls", (), {"query": _FakeQuery(), "__call__": None}))

    created = []

    class FakeCVE:
        query = _FakeQuery()

        def __init__(self, id):
            self.id = id
            self.description = ""
            self.cvss_score = None
            self.affected_products = []
            self.last_updated = None

    monkeypatch.setattr(updater, "CVE", FakeCVE)

    class FakeSession:
        def add(self, obj):
            created.append(obj)

        def commit(self):
            return None

    monkeypatch.setattr(updater.db, "session", FakeSession())

    calls = {"n": 0}

    class FakeTask:
        def delay(self, *args, **kwargs):
            calls["n"] += 1

    monkeypatch.setattr(updater, "send_vulnerability_alerts", FakeTask())

    out = updater.update_nvd_cve()
    assert out["created"] == 1
    assert calls["n"] == 1
