"""Configuration loading for the stock notification agent."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

from stock_agent.models import StockConfig

load_dotenv()


@dataclass
class EmailConfig:
    enabled: bool = True
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    from_address: str = ""
    to_addresses: list[str] = field(default_factory=list)


@dataclass
class SchedulerConfig:
    daily_digest_hour: int = 8
    daily_digest_minute: int = 0
    timezone: str = "Europe/London"


@dataclass
class AppConfig:
    stocks: list[StockConfig]
    email: EmailConfig
    scheduler: SchedulerConfig
    openai_api_key: str = ""
    finnhub_api_key: str = ""
    defaults: dict = field(default_factory=lambda: {"price_change_pct": 2.0, "volume_spike": 1.5})


def load_config(config_path: str | Path = "portfolio.yaml") -> AppConfig:
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(
            f"Configuration file not found: {config_path}. "
            "Copy portfolio.yaml.example to portfolio.yaml and edit it."
        )

    with open(config_path) as f:
        raw = yaml.safe_load(f)

    defaults = raw.get("defaults", {"price_change_pct": 2.0, "volume_spike": 1.5})

    stocks: list[StockConfig] = []
    for s in raw.get("stocks", []):
        thresholds = s.get("alert_thresholds", {})
        stocks.append(
            StockConfig(
                symbol=s["symbol"],
                name=s.get("name", ""),
                price_change_pct=thresholds.get("price_change_pct", defaults["price_change_pct"]),
                volume_spike=thresholds.get("volume_spike", defaults["volume_spike"]),
            )
        )

    email_raw = raw.get("email", {})
    email = EmailConfig(
        enabled=email_raw.get("enabled", True),
        smtp_host=email_raw.get("smtp_host", os.getenv("SMTP_HOST", "")),
        smtp_port=email_raw.get("smtp_port", int(os.getenv("SMTP_PORT", "587"))),
        smtp_user=email_raw.get("smtp_user", os.getenv("SMTP_USER", "")),
        smtp_password=email_raw.get("smtp_password", os.getenv("SMTP_PASSWORD", "")),
        from_address=email_raw.get("from_address", os.getenv("EMAIL_FROM", "")),
        to_addresses=email_raw.get(
            "to_addresses",
            [a.strip() for a in os.getenv("EMAIL_TO", "").split(",") if a.strip()],
        ),
    )

    sched_raw = raw.get("scheduler", {})
    scheduler = SchedulerConfig(
        daily_digest_hour=sched_raw.get("daily_digest_hour", 8),
        daily_digest_minute=sched_raw.get("daily_digest_minute", 0),
        timezone=sched_raw.get("timezone", "Europe/London"),
    )

    return AppConfig(
        stocks=stocks,
        email=email,
        scheduler=scheduler,
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        finnhub_api_key=os.getenv("FINNHUB_API_KEY", ""),
        defaults=defaults,
    )
