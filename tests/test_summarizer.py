"""Tests for AI summarizer."""

from __future__ import annotations

from stock_agent.ai.summarizer import summarize_news
from stock_agent.models import NewsArticle, Sentiment


def test_summarize_no_articles() -> None:
    result = summarize_news("AAPL", "Apple", [], api_key="")
    assert result.symbol == "AAPL"
    assert result.ai_summary == "No recent news found."
    assert result.sentiment == Sentiment.NEUTRAL


def test_summarize_without_api_key() -> None:
    articles = [
        NewsArticle(title="Apple reports record Q4", url="https://example.com", source="Reuters"),
        NewsArticle(title="iPhone sales surge", url="https://example.com", source="Bloomberg"),
    ]
    result = summarize_news("AAPL", "Apple", articles, api_key="")
    assert "Apple reports record Q4" in result.ai_summary
    assert len(result.key_points) == 2
    assert result.sentiment == Sentiment.NEUTRAL


def test_summarize_preserves_articles() -> None:
    articles = [
        NewsArticle(title="Test", url="https://example.com", source="Test Source"),
    ]
    result = summarize_news("AAPL", "Apple", articles, api_key="")
    assert len(result.articles) == 1
    assert result.articles[0].title == "Test"
