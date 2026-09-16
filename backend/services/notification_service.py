"""Centralized alert sender."""

from __future__ import annotations

import os
import smtplib
import logging
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


def send_admin_alert(subject: str, body: str) -> bool:
    sender = os.getenv("ALERT_EMAIL_FROM") or os.getenv("EMAIL_FROM")
    recipient = os.getenv("ALERT_EMAIL_TO") or os.getenv("EMAIL_TO")
    password = os.getenv("GMAIL_APP_PASSWORD")

    if not sender or not recipient or not password:
        logger.warning("Alert email is not configured. subject=%s", subject)
        return False

    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = recipient

        with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
            smtp.starttls()
            smtp.login(sender, password)
            smtp.sendmail(sender, recipient, msg.as_string())

        logger.info("Admin alert sent: %s", subject)
        return True
    except Exception:
        logger.exception("Failed to send admin alert: %s", subject)
        return False
