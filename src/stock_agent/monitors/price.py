"""Price and volume monitoring using yfinance."""

from __future__ import annotations

import logging

import yfinance as yf

from stock_agent.models import Alert, AlertType, PriceData, StockConfig

logger = logging.getLogger(__name__)


def fetch_price_data(stock: StockConfig) -> PriceData | None:
    try:
        ticker = yf.Ticker(stock.symbol)
        info = ticker.info
        if not info or "currentPrice" not in info and "regularMarketPrice" not in info:
            logger.warning("No price data for %s", stock.symbol)
            return None

        current = info.get("currentPrice") or info.get("regularMarketPrice", 0)
        prev_close = info.get("previousClose", info.get("regularMarketPreviousClose", 0))
        change_pct = ((current - prev_close) / prev_close * 100) if prev_close else 0

        return PriceData(
            symbol=stock.symbol,
            name=stock.name or info.get("shortName", stock.symbol),
            current_price=current,
            previous_close=prev_close,
            change_pct=round(change_pct, 2),
            volume=info.get("volume", info.get("regularMarketVolume", 0)),
            avg_volume=info.get("averageVolume", 0),
            currency=info.get("currency", "USD"),
            market_cap=info.get("marketCap"),
            day_high=info.get("dayHigh", info.get("regularMarketDayHigh")),
            day_low=info.get("dayLow", info.get("regularMarketDayLow")),
        )
    except Exception:
        logger.exception("Error fetching price data for %s", stock.symbol)
        return None


def check_price_alerts(stock: StockConfig, price: PriceData) -> list[Alert]:
    alerts: list[Alert] = []

    if abs(price.change_pct) >= stock.price_change_pct:
        direction = "up" if price.change_pct > 0 else "down"
        severity = "critical" if abs(price.change_pct) >= stock.price_change_pct * 2 else "warning"
        details = (
            f"Current: {price.currency} {price.current_price:.2f} | "
            f"Prev Close: {price.currency} {price.previous_close:.2f}"
        )
        if price.day_low is not None and price.day_high is not None:
            details += (
                f" | Day Range: {price.currency} {price.day_low:.2f}"
                f" - {price.currency} {price.day_high:.2f}"
            )
        alerts.append(
            Alert(
                alert_type=AlertType.PRICE_CHANGE,
                symbol=price.symbol,
                name=price.name,
                headline=(
                    f"{price.name} ({price.symbol}) is "
                    f"{direction} {abs(price.change_pct):.1f}%"
                ),
                details=details,
                severity=severity,
                data={"change_pct": price.change_pct, "price": price.current_price},
            )
        )

    if price.avg_volume and price.volume:
        volume_ratio = price.volume / price.avg_volume
        if volume_ratio >= stock.volume_spike:
            alerts.append(
                Alert(
                    alert_type=AlertType.VOLUME_SPIKE,
                    symbol=price.symbol,
                    name=price.name,
                    headline=(
                        f"{price.name} ({price.symbol}) volume is "
                        f"{volume_ratio:.1f}x its average"
                    ),
                    details=(
                        f"Volume: {price.volume:,} | "
                        f"Avg Volume: {price.avg_volume:,}"
                    ),
                    severity="warning",
                    data={"volume_ratio": volume_ratio},
                )
            )

    return alerts
