"""Data models for the stock notification agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class AlertType(Enum):
    PRICE_CHANGE = "price_change"
    VOLUME_SPIKE = "volume_spike"
    EARNINGS = "earnings"
    DIVIDEND = "dividend"
    NEWS = "news"


class Sentiment(Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


@dataclass
class StockConfig:
    symbol: str
    name: str = ""
    price_change_pct: float = 2.0
    volume_spike: float = 1.5


@dataclass
class PriceData:
    symbol: str
    name: str
    current_price: float
    previous_close: float
    change_pct: float
    volume: int
    avg_volume: int
    currency: str = "USD"
    market_cap: float | None = None
    day_high: float | None = None
    day_low: float | None = None


@dataclass
class NewsArticle:
    title: str
    url: str
    source: str
    published: datetime | None = None
    summary: str = ""
    related_symbols: list[str] = field(default_factory=list)


@dataclass
class NewsSummary:
    symbol: str
    name: str
    articles: list[NewsArticle]
    ai_summary: str = ""
    sentiment: Sentiment = Sentiment.NEUTRAL
    key_points: list[str] = field(default_factory=list)


@dataclass
class EarningsEvent:
    symbol: str
    name: str
    date: datetime
    eps_estimate: float | None = None
    eps_actual: float | None = None
    revenue_estimate: float | None = None
    revenue_actual: float | None = None


@dataclass
class DividendInfo:
    symbol: str
    name: str
    dividend_rate: float | None = None
    dividend_yield: float | None = None
    ex_date: datetime | None = None
    pay_date: datetime | None = None


@dataclass
class Alert:
    alert_type: AlertType
    symbol: str
    name: str
    headline: str
    details: str
    timestamp: datetime = field(default_factory=datetime.now)
    severity: str = "info"  # info, warning, critical
    data: dict | None = None
