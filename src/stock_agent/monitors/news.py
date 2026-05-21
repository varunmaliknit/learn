"""News monitoring via yfinance and Google News RSS."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

import feedparser
import requests

from stock_agent.models import NewsArticle, StockConfig

logger = logging.getLogger(__name__)

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=en&gl=US&ceid=US:en"


def _is_relevant(title: str, stock: StockConfig) -> bool:
    """Check if a headline is relevant to the specific stock."""
    title_lower = title.lower()
    symbol_clean = stock.symbol.replace(".L", "").replace(".AX", "").replace("=F", "").lower()

    name_lower = (stock.name or "").lower()
    name_words = [w for w in name_lower.split() if len(w) > 2]

    if symbol_clean in re.split(r"[\s\(\)\[\]:,;'\"\-/]", title_lower):
        return True

    if name_lower and name_lower in title_lower:
        return True

    if name_words and any(w in title_lower for w in name_words if len(w) > 3):
        return True

    ticker_pattern = rf'\b{re.escape(stock.symbol.upper())}\b'
    if re.search(ticker_pattern, title):
        return True

    return False


def fetch_yfinance_news(stock: StockConfig) -> list[NewsArticle]:
    try:
        import yfinance as yf

        ticker = yf.Ticker(stock.symbol)
        raw_news = ticker.news or []
        articles: list[NewsArticle] = []
        for item in raw_news:
            content = item.get("content", item) if isinstance(item, dict) else {}
            if isinstance(content, dict):
                title = content.get("title", "")
                url = content.get("canonicalUrl", {})
                if isinstance(url, dict):
                    url = url.get("url", "")
                provider = content.get("provider", {})
                if isinstance(provider, dict):
                    source = provider.get("displayName", "Yahoo Finance")
                else:
                    source = "Yahoo Finance"
                pub_date = content.get("pubDate")
            else:
                title = item.get("title", "") if isinstance(item, dict) else str(item)
                url = item.get("link", "") if isinstance(item, dict) else ""
                source = "Yahoo Finance"
                pub_date = None

            if not title:
                continue

            published = None
            if pub_date:
                try:
                    published = datetime.fromisoformat(str(pub_date).replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass

            articles.append(
                NewsArticle(
                    title=title,
                    url=url if isinstance(url, str) else "",
                    source=source,
                    published=published,
                    related_symbols=[stock.symbol],
                )
            )
        return articles
    except Exception:
        logger.exception("Error fetching yfinance news for %s", stock.symbol)
        return []


def fetch_google_news(stock: StockConfig, max_articles: int = 8) -> list[NewsArticle]:
    search_name = stock.name or stock.symbol
    query = f'"{search_name}" stock OR shares OR earnings OR dividend'
    url = GOOGLE_NEWS_RSS.format(query=requests.utils.quote(query))
    try:
        feed = feedparser.parse(url)
        articles: list[NewsArticle] = []
        for entry in feed.entries[:max_articles]:
            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                try:
                    published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                except (ValueError, TypeError):
                    pass

            articles.append(
                NewsArticle(
                    title=entry.get("title", ""),
                    url=entry.get("link", ""),
                    source=entry.get("source", {}).get("title", "Google News")
                    if isinstance(entry.get("source"), dict)
                    else "Google News",
                    published=published,
                    related_symbols=[stock.symbol],
                )
            )
        return articles
    except Exception:
        logger.exception("Error fetching Google News for %s", stock.symbol)
        return []


def _is_recent(article: NewsArticle, max_age_hours: int = 24) -> bool:
    """Check if an article was published within the last max_age_hours."""
    if article.published is None:
        return True
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    pub = article.published
    if pub.tzinfo is None:
        pub = pub.replace(tzinfo=timezone.utc)
    return pub >= cutoff


def fetch_all_news(stock: StockConfig, max_per_source: int = 8) -> list[NewsArticle]:
    yf_news = fetch_yfinance_news(stock)
    google_news = fetch_google_news(stock, max_articles=max_per_source)

    seen_titles: set[str] = set()
    deduplicated: list[NewsArticle] = []
    for article in yf_news + google_news:
        normalized = article.title.lower().strip()
        if normalized not in seen_titles and article.title:
            seen_titles.add(normalized)
            deduplicated.append(article)

    recent = [a for a in deduplicated if _is_recent(a)]

    relevant = [a for a in recent if _is_relevant(a.title, stock)]

    if len(relevant) < 3:
        relevant = recent[:8]

    return relevant[:10]
