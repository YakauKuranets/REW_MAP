# -*- coding: utf-8 -*-
"""Security awareness campaign manager.

This module supports authorized phishing-resilience training campaigns
for employee awareness programs.
"""

from __future__ import annotations

import imaplib
import logging
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, List

from app.ai.predictive_advisor import PredictiveAdvisor

logger = logging.getLogger(__name__)


class PhishingCampaignManager:
    """Manager for awareness campaigns with SMTP send and IMAP stats collection."""

    def __init__(self) -> None:
        self.llm = PredictiveAdvisor()
        self.campaigns: dict[str, dict] = {}

    def create_campaign(self, name: str, target_emails: List[str], template_type: str = "generic") -> str:
        campaign_id = f"camp_{int(time.time())}"
        prompt = (
            "Create a SAFE security-awareness email template for employee training. "
            f"Template type: {template_type}. "
            "Return plain HTML only; no malicious links or credential collection forms."
        )
        content = self.llm._call_llm(prompt, max_tokens=500) or (
            "<html><body><h3>Security Awareness Training</h3>"
            "<p>Это учебная рассылка по кибербезопасности.</p></body></html>"
        )

        self.campaigns[campaign_id] = {
            "id": campaign_id,
            "name": name,
            "targets": list(target_emails or []),
            "template": content,
            "status": "created",
            "sent_count": 0,
            "opened_count": 0,
            "clicked_count": 0,
            "created_at": time.time(),
        }
        return campaign_id

    def send_campaign(self, campaign_id: str, smtp_config: Dict) -> Dict:
        campaign = self.campaigns.get(campaign_id)
        if not campaign:
            return {"error": "Campaign not found"}

        results = {"sent": [], "failed": []}
        try:
            server = smtplib.SMTP(smtp_config["host"], int(smtp_config.get("port", 587)), timeout=20)
            if smtp_config.get("use_tls", True):
                server.starttls()
            if smtp_config.get("username"):
                server.login(smtp_config["username"], smtp_config.get("password", ""))

            for email in campaign["targets"]:
                msg = MIMEMultipart()
                msg["From"] = smtp_config.get("from", "security-training@local")
                msg["To"] = email
                msg["Subject"] = "Security Awareness Training Notification"
                msg.attach(MIMEText(campaign["template"], "html", _charset="utf-8"))
                try:
                    server.send_message(msg)
                    results["sent"].append(email)
                    campaign["sent_count"] += 1
                except Exception as exc:
                    results["failed"].append({"email": email, "error": str(exc)})

            server.quit()
            campaign["status"] = "completed"
        except Exception as exc:
            logger.error("SMTP error: %s", exc)
            campaign["status"] = "failed"

        return results

    def track_results(self, campaign_id: str, imap_config: Dict) -> Dict:
        campaign = self.campaigns.get(campaign_id)
        if not campaign:
            return {"error": "Campaign not found"}

        try:
            imap = imaplib.IMAP4_SSL(imap_config["host"], int(imap_config.get("port", 993)))
            imap.login(imap_config["username"], imap_config["password"])
            imap.select("INBOX")
            _, data = imap.search(None, 'SUBJECT "Security Awareness Training"')
            ids = (data[0].split() if data and data[0] else [])
            campaign["opened_count"] += len(ids)
            imap.close()
            imap.logout()
        except Exception as exc:
            logger.error("IMAP error: %s", exc)

        sent = int(campaign["sent_count"] or 0)
        clicked = int(campaign["clicked_count"] or 0)
        return {
            "campaign_id": campaign_id,
            "sent": sent,
            "opened": int(campaign["opened_count"] or 0),
            "clicked": clicked,
            "conversion_rate": (clicked / sent * 100.0) if sent > 0 else 0.0,
        }
