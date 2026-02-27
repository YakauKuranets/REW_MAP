from __future__ import annotations

import tempfile
from pathlib import Path

from flask import Flask

from app.reports.email_sender import ReportMailer


class _FakeSMTP:
    def __init__(self, *args, **kwargs):
        self.started_tls = False
        self.logged_in = False
        self.sent = False

    def starttls(self):
        self.started_tls = True

    def login(self, user, pwd):
        self.logged_in = bool(user and pwd)

    def send_message(self, msg):
        self.sent = True

    def quit(self):
        return None


def test_report_mailer_send(monkeypatch):
    app = Flask(__name__)
    app.config.update(
        MAIL_SERVER="smtp.example.com",
        MAIL_PORT=587,
        MAIL_USERNAME="u@example.com",
        MAIL_PASSWORD="secret",
        MAIL_USE_TLS=True,
    )

    monkeypatch.setattr("smtplib.SMTP", _FakeSMTP)

    fd, path = tempfile.mkstemp(suffix=".pdf")
    Path(path).write_bytes(b"pdf")

    with app.app_context():
        mailer = ReportMailer()
        ok = mailer.send_report(["a@example.com"], "subj", "body", pdf_path=path)

    assert ok is True
