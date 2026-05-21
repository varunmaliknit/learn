"""Email notifier using SMTP."""

from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from stock_agent.config import EmailConfig
from stock_agent.notifiers.base import BaseNotifier

logger = logging.getLogger(__name__)


class EmailNotifier(BaseNotifier):
    def __init__(self, config: EmailConfig) -> None:
        self.config = config

    def send(self, subject: str, body_html: str, body_text: str) -> bool:
        if not self.config.enabled:
            logger.info("Email notifications disabled")
            return False

        if not all([
            self.config.smtp_host,
            self.config.smtp_user,
            self.config.smtp_password,
            self.config.from_address,
            self.config.to_addresses,
        ]):
            logger.error("Email configuration incomplete — check SMTP settings")
            return False

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.config.from_address
        msg["To"] = ", ".join(self.config.to_addresses)

        msg.attach(MIMEText(body_text, "plain"))
        msg.attach(MIMEText(body_html, "html"))

        try:
            with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(self.config.smtp_user, self.config.smtp_password)
                server.sendmail(
                    self.config.from_address,
                    self.config.to_addresses,
                    msg.as_string(),
                )
            logger.info("Email sent: %s", subject)
            return True
        except Exception:
            logger.exception("Failed to send email")
            return False
