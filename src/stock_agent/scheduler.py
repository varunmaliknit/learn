"""Scheduler for daily digest delivery."""

from __future__ import annotations

import logging
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from stock_agent.config import AppConfig
from stock_agent.digest import build_html_digest, build_text_digest, gather_digest
from stock_agent.notifiers.email import EmailNotifier

logger = logging.getLogger(__name__)


def send_daily_digest(config: AppConfig) -> None:
    logger.info("Starting daily digest generation at %s", datetime.now().isoformat())

    try:
        data = gather_digest(config)
        html = build_html_digest(data, config)
        text = build_text_digest(data, config)

        date_str = data["generated_at"].strftime("%b %d, %Y")
        subject = f"📊 Daily Portfolio Digest — {date_str}"

        notifier = EmailNotifier(config.email)
        success = notifier.send(subject, html, text)

        if success:
            logger.info("Daily digest sent successfully")
        else:
            logger.error("Failed to send daily digest")
    except Exception:
        logger.exception("Error generating daily digest")


def create_scheduler(config: AppConfig) -> BlockingScheduler:
    scheduler = BlockingScheduler()

    trigger = CronTrigger(
        hour=config.scheduler.daily_digest_hour,
        minute=config.scheduler.daily_digest_minute,
        timezone=config.scheduler.timezone,
    )

    scheduler.add_job(
        send_daily_digest,
        trigger=trigger,
        args=[config],
        id="daily_digest",
        name="Daily Portfolio Digest",
        misfire_grace_time=3600,
    )

    logger.info(
        "Scheduled daily digest at %02d:%02d %s",
        config.scheduler.daily_digest_hour,
        config.scheduler.daily_digest_minute,
        config.scheduler.timezone,
    )

    return scheduler
