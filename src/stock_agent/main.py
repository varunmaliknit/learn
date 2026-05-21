"""Entry point for the stock portfolio notification agent."""

from __future__ import annotations

import argparse
import logging
import sys

from stock_agent.config import load_config
from stock_agent.digest import build_html_digest, build_text_digest, gather_digest
from stock_agent.notifiers.email import EmailNotifier
from stock_agent.scheduler import create_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Stock Portfolio Notification Agent")
    parser.add_argument(
        "--config",
        default="portfolio.yaml",
        help="Path to portfolio config file (default: portfolio.yaml)",
    )
    parser.add_argument(
        "--run-once",
        action="store_true",
        help="Generate and send digest immediately, then exit",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate digest and print to stdout (don't send email)",
    )
    args = parser.parse_args()

    try:
        config = load_config(args.config)
    except FileNotFoundError as e:
        logger.error(str(e))
        sys.exit(1)

    logger.info("Loaded %d stocks from config", len(config.stocks))

    if args.dry_run:
        data = gather_digest(config)
        text = build_text_digest(data, config)
        print(text)
        return

    if args.run_once:
        data = gather_digest(config)
        html = build_html_digest(data, config)
        text = build_text_digest(data, config)
        date_str = data["generated_at"].strftime("%b %d, %Y")
        subject = f"📊 Daily Portfolio Digest — {date_str}"

        notifier = EmailNotifier(config.email)
        success = notifier.send(subject, html, text)
        if success:
            logger.info("Digest sent successfully")
        else:
            logger.error("Failed to send digest")
        return

    logger.info(
        "Starting scheduler — digest will be sent daily at %02d:%02d %s",
        config.scheduler.daily_digest_hour,
        config.scheduler.daily_digest_minute,
        config.scheduler.timezone,
    )
    scheduler = create_scheduler(config)
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down scheduler")
        scheduler.shutdown()


if __name__ == "__main__":
    main()
