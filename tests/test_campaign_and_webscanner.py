from __future__ import annotations

from app.phishing.campaign_manager import PhishingCampaignManager
from app.webapp.web_scanner import WebAppScanner


def test_campaign_create_and_track(monkeypatch):
    mgr = PhishingCampaignManager()
    monkeypatch.setattr(mgr.llm, "_call_llm", lambda *a, **k: "<html>training</html>")

    cid = mgr.create_campaign("test", ["a@example.com"])
    assert cid.startswith("camp_")
    assert mgr.campaigns[cid]["template"]

    class FakeIMAP:
        def __init__(self, host, port):
            pass

        def login(self, u, p):
            return "OK", []

        def select(self, box):
            return "OK", []

        def search(self, *args):
            return "OK", [b"1 2"]

        def close(self):
            return None

        def logout(self):
            return None

    monkeypatch.setattr("imaplib.IMAP4_SSL", FakeIMAP)
    stats = mgr.track_results(cid, {"host": "imap.example.com", "port": 993, "username": "u", "password": "p"})
    assert stats["opened"] >= 2


def test_web_scanner_parsers(monkeypatch, tmp_path):
    scanner = WebAppScanner(nuclei_path="nuclei", nikto_path="nikto")

    def fake_run(cmd, capture_output=True, timeout=0, check=False):
        if "-json" in cmd:
            out = cmd[cmd.index("-o") + 1]
            with open(out, "w", encoding="utf-8") as f:
                f.write('{"template-id":"t1","info":{"name":"x","severity":"high"},"matched-at":"http://x"}\n')
        else:
            out = cmd[cmd.index("-o") + 1]
            with open(out, "w", encoding="utf-8") as f:
                f.write('+ OSVDB-1 Test finding\n')

    monkeypatch.setattr("subprocess.run", fake_run)

    n = scanner.scan_with_nuclei("http://example.com")
    k = scanner.scan_with_nikto("http://example.com")
    assert n and n[0]["template"] == "t1"
    assert k and k[0]["type"] == "nikto_finding"
