"""Tests for data models."""

from __future__ import annotations

from datetime import datetime, timezone

from stock_agent.models import (
    Alert,
    AlertType,
    NewsArticle,
    NewsSummary,
    PriceData,
    Sentiment,
    StockConfig,
)


def test_stock_config_defaults() -> None:
    stock = StockConfig(symbol="AAPL")
    assert stock.price_change_pct == 2.0
    assert stock.volume_spike == 1.5
    assert stock.name == ""


def test_price_data() -> None:
    price = PriceData(
        symbol="AAPL",
        name="Apple",
        current_price=180.0,
        previous_close=175.0,
        change_pct=2.86,
        volume=50_000_000,
        avg_volume=40_000_000,
    )
    assert price.currency == "USD"
    assert price.change_pct == 2.86


def test_news_article() -> None:
    article = NewsArticle(
        title="Test article",
        url="https://example.com",
        source="Test Source",
        published=datetime.now(timezone.utc),
    )
    assert article.related_symbols == []
    assert article.summary == ""


def test_alert_creation() -> None:
    alert = Alert(
        alert_type=AlertType.PRICE_CHANGE,
        symbol="AAPL",
        name="Apple",
        headline="Apple is up 5%",
        details="Current: $180.00",
        severity="warning",
    )
    assert alert.alert_type == AlertType.PRICE_CHANGE
    assert alert.severity == "warning"
    assert isinstance(alert.timestamp, datetime)


def test_sentiment_enum() -> None:
    assert Sentiment.BULLISH.value == "bullish"
    assert Sentiment.BEARISH.value == "bearish"
    assert Sentiment.NEUTRAL.value == "neutral"


def test_news_summary_defaults() -> None:
    summary = NewsSummary(symbol="AAPL", name="Apple", articles=[])
    assert summary.ai_summary == ""
    assert summary.sentiment == Sentiment.NEUTRAL
    assert summary.key_points == []
