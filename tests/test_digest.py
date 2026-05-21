"""Tests for digest builder."""

from __future__ import annotations

from datetime import datetime, timezone

from stock_agent.config import AppConfig, EmailConfig, SchedulerConfig, StockConfig
from stock_agent.digest import build_html_digest, build_text_digest
from stock_agent.models import NewsSummary, PriceData, Sentiment


def _make_config() -> AppConfig:
    return AppConfig(
        stocks=[StockConfig(symbol="AAPL", name="Apple")],
        email=EmailConfig(),
        scheduler=SchedulerConfig(),
    )


def _make_digest_data() -> dict:
    return {
        "prices": [
            PriceData(
                symbol="AAPL",
                name="Apple",
                current_price=180.0,
                previous_close=175.0,
                change_pct=2.86,
                volume=50_000_000,
                avg_volume=40_000_000,
                day_high=182.0,
                day_low=178.0,
            )
        ],
        "alerts": [],
        "news_summaries": [
            NewsSummary(
                symbol="AAPL",
                name="Apple",
                articles=[],
                ai_summary="Apple had a strong day.",
                sentiment=Sentiment.BULLISH,
                key_points=["Revenue up 10%"],
            )
        ],
        "earnings": [],
        "dividends": [],
        "generated_at": datetime(2025, 1, 15, 8, 0, tzinfo=timezone.utc),
    }


def test_build_html_digest() -> None:
    config = _make_config()
    data = _make_digest_data()
    html = build_html_digest(data, config)
    assert "Daily Portfolio Digest" in html
    assert "Apple" in html
    assert "AAPL" in html
    assert "180.00" in html
    assert "2.86%" in html


def test_build_text_digest() -> None:
    config = _make_config()
    data = _make_digest_data()
    text = build_text_digest(data, config)
    assert "DAILY PORTFOLIO DIGEST" in text
    assert "Apple" in text
    assert "AAPL" in text
    assert "180.00" in text


def test_html_digest_includes_news_summary() -> None:
    config = _make_config()
    data = _make_digest_data()
    html = build_html_digest(data, config)
    assert "Apple had a strong day" in html
    assert "Bullish" in html


def test_text_digest_includes_news_summary() -> None:
    config = _make_config()
    data = _make_digest_data()
    text = build_text_digest(data, config)
    assert "Apple had a strong day" in text
    assert "Bullish" in text
