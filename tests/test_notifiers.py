"""Tests for notifiers."""

from __future__ import annotations

from stock_agent.config import EmailConfig
from stock_agent.notifiers.email import EmailNotifier


def test_email_notifier_disabled() -> None:
    config = EmailConfig(enabled=False)
    notifier = EmailNotifier(config)
    result = notifier.send("Test", "<p>Test</p>", "Test")
    assert result is False


def test_email_notifier_incomplete_config() -> None:
    config = EmailConfig(enabled=True, smtp_host="", smtp_user="", smtp_password="")
    notifier = EmailNotifier(config)
    result = notifier.send("Test", "<p>Test</p>", "Test")
    assert result is False
