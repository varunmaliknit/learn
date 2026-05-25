"""Render the approval email (HTML + plain text) and send it via SMTP."""

from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from linkedin_agent.config import EmailConfig
from linkedin_agent.models import Draft

logger = logging.getLogger(__name__)


_TEMPLATES_DIR = Path(__file__).parent / "templates"


def _jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        # `.html.j2` ends in `.j2`, not `.html` — include both extensions explicitly.
        autoescape=select_autoescape(
            enabled_extensions=("html", "htm", "xml", "j2"),
            default_for_string=True,
        ),
    )


def render_html(
    draft: Draft,
    approve_url: str,
    reject_url: str,
    issue_url: str,
    issue_edit_url: str,
) -> str:
    env = _jinja_env()
    tpl = env.get_template("preview_email.html.j2")
    return tpl.render(
        draft=draft,
        approve_url=approve_url,
        reject_url=reject_url,
        issue_url=issue_url,
        issue_edit_url=issue_edit_url,
    )


def render_text(draft: Draft, approve_url: str, reject_url: str, issue_url: str) -> str:
    lines = [
        f"LinkedIn draft — {draft.draft_id}",
        "",
        "=" * 60,
        draft.full_text(),
        "=" * 60,
        "",
        f"Approve & post: {approve_url}",
        f"Reject:         {reject_url}",
        f"Edit on GitHub: {issue_url}",
        "",
        "Sources:",
    ]
    for t in draft.trends:
        lines.append(f"  - {t.title}")
        lines.append(f"    {t.url}")
        lines.append(f"    impact {t.impact_score:.1f}  ·  {t.short_source()}")
    return "\n".join(lines)


def send_email(
    config: EmailConfig,
    subject: str,
    body_html: str,
    body_text: str,
) -> bool:
    if not config.enabled:
        logger.info("Email disabled in config")
        return False
    missing = [
        name
        for name, val in (
            ("smtp_host", config.smtp_host),
            ("smtp_user", config.smtp_user),
            ("smtp_password", config.smtp_password),
            ("from_address", config.from_address),
            ("to_addresses", config.to_addresses),
        )
        if not val
    ]
    if missing:
        logger.error("Email config incomplete; missing: %s", ", ".join(missing))
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = config.from_address
    msg["To"] = ", ".join(config.to_addresses)
    msg.attach(MIMEText(body_text, "plain", "utf-8"))
    msg.attach(MIMEText(body_html, "html", "utf-8"))

    try:
        with smtplib.SMTP(config.smtp_host, config.smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(config.smtp_user, config.smtp_password)
            server.sendmail(config.from_address, config.to_addresses, msg.as_string())
    except Exception as e:  # noqa: BLE001
        logger.error("SMTP send failed: %s", e)
        return False
    logger.info("Email sent to %s", ", ".join(config.to_addresses))
    return True
