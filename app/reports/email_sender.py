# -*- coding: utf-8 -*-
"""Automated email delivery for diagnostic reports via SMTP."""

from __future__ import annotations

import logging
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

from compat_flask import current_app

logger = logging.getLogger(__name__)


class ReportMailer:
    """Sends report notifications and PDF attachments using SMTP settings."""

    def __init__(
        self,
        smtp_server: Optional[str] = None,
        smtp_port: Optional[int] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        use_tls: Optional[bool] = None,
    ) -> None:
        cfg = current_app.config if current_app else {}
        self.smtp_server = smtp_server or cfg.get("MAIL_SERVER", "")
        self.smtp_port = int(smtp_port or cfg.get("MAIL_PORT", 587))
        self.username = username or cfg.get("MAIL_USERNAME", "")
        self.password = password or cfg.get("MAIL_PASSWORD", "")
        self.use_tls = bool(cfg.get("MAIL_USE_TLS", True) if use_tls is None else use_tls)

    def send_report(
        self,
        to_emails: list[str],
        subject: str,
        body: str,
        pdf_path: Optional[str] = None,
        attachments: Optional[list[str]] = None,
    ) -> bool:
        if not to_emails:
            return False

        msg = MIMEMultipart()
        msg["From"] = self.username
        msg["To"] = ", ".join(to_emails)
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", _charset="utf-8"))

        if pdf_path:
            self._attach_file(msg, pdf_path, subtype="pdf")
        for item in attachments or []:
            self._attach_file(msg, item)

        if not (self.smtp_server and self.username and self.password):
            logger.warning("SMTP is not fully configured; skip email send")
            return False

        try:
            if self.use_tls:
                server = smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=20)
                server.starttls()
            else:
                server = smtplib.SMTP_SSL(self.smtp_server, self.smtp_port, timeout=20)

            server.login(self.username, self.password)
            server.send_message(msg)
            server.quit()
            logger.info("Report sent to %s", to_emails)
            return True
        except Exception:
            logger.exception("Failed to send report email")
            return False

    @staticmethod
    def _attach_file(msg: MIMEMultipart, file_path: str, subtype: Optional[str] = None) -> None:
        path = Path(file_path)
        if not path.exists() or not path.is_file():
            return
        with open(path, "rb") as stream:
            part = MIMEApplication(stream.read(), _subtype=subtype) if subtype else MIMEApplication(stream.read())
        part.add_header("Content-Disposition", "attachment", filename=path.name)
        msg.attach(part)
