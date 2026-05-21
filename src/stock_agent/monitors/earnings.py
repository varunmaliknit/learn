"""Earnings calendar monitoring using yfinance."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import yfinance as yf

from stock_agent.models import EarningsEvent, StockConfig

logger = logging.getLogger(__name__)


def fetch_upcoming_earnings(stock: StockConfig, days_ahead: int = 30) -> EarningsEvent | None:
    try:
        ticker = yf.Ticker(stock.symbol)
        cal = ticker.calendar
        if cal is None or (isinstance(cal, dict) and not cal):
            return None

        earnings_date = None
        if isinstance(cal, dict):
            raw_date = cal.get("Earnings Date")
            if isinstance(raw_date, list) and raw_date:
                raw_date = raw_date[0]
            if isinstance(raw_date, datetime):
                earnings_date = raw_date
            elif isinstance(raw_date, str):
                try:
                    earnings_date = datetime.fromisoformat(raw_date)
                except ValueError:
                    pass
            eps_est = cal.get("Earnings Average") or cal.get("EPS Estimate")
            rev_est = cal.get("Revenue Average") or cal.get("Revenue Estimate")
        else:
            return None

        if earnings_date is None:
            return None

        now = datetime.now(timezone.utc)
        if earnings_date.tzinfo is None:
            earnings_date = earnings_date.replace(tzinfo=timezone.utc)

        if earnings_date < now - timedelta(days=1):
            return None
        if earnings_date > now + timedelta(days=days_ahead):
            return None

        name = stock.name or ticker.info.get("shortName", stock.symbol)
        return EarningsEvent(
            symbol=stock.symbol,
            name=name,
            date=earnings_date,
            eps_estimate=float(eps_est) if eps_est else None,
            revenue_estimate=float(rev_est) if rev_est else None,
        )
    except Exception:
        logger.exception("Error fetching earnings for %s", stock.symbol)
        return None
