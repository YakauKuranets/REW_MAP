from __future__ import annotations

import app.tasks.reports_delivery as delivery


class _FakeSub:
    def __init__(self, email):
        self.email = email


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return list(self._rows)


def test_send_vulnerability_alerts(monkeypatch):
    monkeypatch.setattr(delivery.AlertSubscription, "query", _FakeQuery([_FakeSub("a@x"), _FakeSub("b@x")]))

    sent = {"count": 0}

    class FakeMailer:
        def send_report(self, to_emails, subject, body, **kwargs):
            sent["count"] += 1
            return True

    monkeypatch.setattr(delivery, "ReportMailer", FakeMailer)

    out = delivery.send_vulnerability_alerts("CVE-1", "desc", 9.1, "dev1")
    assert out["sent"] == 2
    assert sent["count"] == 2


def test_generate_and_email_report_cleans_tmp(monkeypatch, tmp_path):
    pdf = tmp_path / "report_1.pdf"

    def fake_generate(task_id, output):
        pdf.write_bytes(b"pdf")
        return str(pdf)

    class FakeMailer:
        def send_report(self, *args, **kwargs):
            return True

    monkeypatch.setattr(delivery, "generate_report", fake_generate)
    monkeypatch.setattr(delivery, "ReportMailer", FakeMailer)

    out = delivery.generate_and_email_report(1, ["a@x"])
    assert out["ok"] is True
    assert not pdf.exists()
