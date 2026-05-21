"""Dividend monitoring using yfinance."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import yfinance as yf

from stock_agent.models import DividendInfo, StockConfig

logger = logging.getLogger(__name__)


def fetch_dividend_info(stock: StockConfig) -> DividendInfo | None:
    try:
        ticker = yf.Ticker(stock.symbol)
        info = ticker.info
        if not info:
            return None

        dividend_rate = info.get("dividendRate")
        dividend_yield = info.get("dividendYield")

        if not dividend_rate and not dividend_yield:
            return None

        ex_date_ts = info.get("exDividendDate")
        ex_date = None
        if ex_date_ts:
            if isinstance(ex_date_ts, (int, float)):
                ex_date = datetime.fromtimestamp(ex_date_ts, tz=timezone.utc)
            elif isinstance(ex_date_ts, str):
                try:
                    ex_date = datetime.fromisoformat(ex_date_ts)
                except ValueError:
                    pass

        name = stock.name or info.get("shortName", stock.symbol)
        return DividendInfo(
            symbol=stock.symbol,
            name=name,
            dividend_rate=dividend_rate,
            dividend_yield=round(dividend_yield * 100, 2) if dividend_yield else None,
            ex_date=ex_date,
        )
    except Exception:
        logger.exception("Error fetching dividend info for %s", stock.symbol)
        return None
