"""Tests for price monitoring logic."""

from __future__ import annotations

from stock_agent.models import AlertType, PriceData, StockConfig
from stock_agent.monitors.price import check_price_alerts


def test_price_alert_triggered() -> None:
    stock = StockConfig(symbol="AAPL", name="Apple", price_change_pct=2.0)
    price = PriceData(
        symbol="AAPL",
        name="Apple",
        current_price=180.0,
        previous_close=170.0,
        change_pct=5.88,
        volume=50_000_000,
        avg_volume=40_000_000,
    )
    alerts = check_price_alerts(stock, price)
    assert len(alerts) >= 1
    price_alerts = [a for a in alerts if a.alert_type == AlertType.PRICE_CHANGE]
    assert len(price_alerts) == 1
    assert "5.9%" in price_alerts[0].headline
    assert price_alerts[0].severity == "critical"  # 5.88% >= 2*2.0


def test_no_price_alert_within_threshold() -> None:
    stock = StockConfig(symbol="AAPL", name="Apple", price_change_pct=5.0)
    price = PriceData(
        symbol="AAPL",
        name="Apple",
        current_price=180.0,
        previous_close=175.0,
        change_pct=2.86,
        volume=40_000_000,
        avg_volume=40_000_000,
    )
    alerts = check_price_alerts(stock, price)
    price_alerts = [a for a in alerts if a.alert_type == AlertType.PRICE_CHANGE]
    assert len(price_alerts) == 0


def test_volume_spike_alert() -> None:
    stock = StockConfig(symbol="AAPL", name="Apple", volume_spike=1.5)
    price = PriceData(
        symbol="AAPL",
        name="Apple",
        current_price=180.0,
        previous_close=179.0,
        change_pct=0.56,
        volume=80_000_000,
        avg_volume=40_000_000,
    )
    alerts = check_price_alerts(stock, price)
    vol_alerts = [a for a in alerts if a.alert_type == AlertType.VOLUME_SPIKE]
    assert len(vol_alerts) == 1
    assert "2.0x" in vol_alerts[0].headline


def test_negative_price_change_alert() -> None:
    stock = StockConfig(symbol="AAPL", name="Apple", price_change_pct=2.0)
    price = PriceData(
        symbol="AAPL",
        name="Apple",
        current_price=165.0,
        previous_close=175.0,
        change_pct=-5.71,
        volume=40_000_000,
        avg_volume=40_000_000,
    )
    alerts = check_price_alerts(stock, price)
    price_alerts = [a for a in alerts if a.alert_type == AlertType.PRICE_CHANGE]
    assert len(price_alerts) == 1
    assert "down" in price_alerts[0].headline
