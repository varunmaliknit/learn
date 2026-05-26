"""Tests for the listing-URL filter and related search helpers."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from linkedin_agent.models import Trend
from linkedin_agent.search import (
    _is_aggregator_url,
    _is_listing_url,
    _parse_published_at,
    score_rss_items,
)


@pytest.mark.parametrize(
    "url",
    [
        # Search / filter query params
        "https://newsroom.ibm.com/press-releases-artificial-intelligence?keywords=2026&l=25",
        "https://example.com/articles?search=ai",
        "https://example.com/posts?q=openai",
        "https://example.com/x?tag=ml",
        "https://example.com/x?category=ai",
        "https://example.com/x?topic=research",
        # Path segments
        "https://example.com/category/ai/",
        "https://example.com/tags/llm/",
        "https://example.com/topics/agents/",
        # Last-segment category pages
        "https://www.sciencedaily.com/news/computers_math/artificial_intelligence/",
        "https://example.com/foo/ai/",
        "https://example.com/foo/machine-learning/",
        "https://example.com/foo/generative-ai/",
        "https://example.com/press-releases/",
        "https://example.com/research",
        # Bare domain
        "https://example.com",
        "https://example.com/",
        "",
    ],
)
def test_is_listing_url_positives(url: str) -> None:
    assert _is_listing_url(url) is True, f"expected listing: {url}"


@pytest.mark.parametrize(
    "url",
    [
        # Specific articles with hyphenated slugs
        "https://blog.google/innovation-and-ai/technology/ai/google-io-2026-all-our-announcements/",
        "https://openai.com/index/gpt-5-launch",
        "https://www.anthropic.com/news/claude-4-launch",
        "https://techcrunch.com/2026/05/22/openai-files-for-ipo/",
        # arXiv
        "https://arxiv.org/abs/2405.12345",
        # Specific path with year
        "https://www.theverge.com/2026/05/24/ai-act-eu-enters-force",
        # Specific named capability
        "https://openai.com/research/superalignment-update",
        # Bloomberg article-style path
        "https://www.bloomberg.com/news/articles/2026-05-22/openai-ipo-filing-25b-revenue",
    ],
)
def test_is_listing_url_negatives(url: str) -> None:
    assert _is_listing_url(url) is False, f"expected NOT listing: {url}"


@pytest.mark.parametrize(
    "url",
    [
        # Known aggregator hosts
        "https://aitoolsrecap.com/Blog/ai-tools-updates-may-2026",
        "https://ainews.com/article/foo",
        "https://aiweeklynews.com/2026/05/22/foo-bar",
        "https://www.buildfastwithai.com/blogs/ai-news-today-may-25-2026",
        # ai-news slug pattern (variant)
        "https://example.com/blogs/ai-news-today-may-25-2026",
        "https://example.com/2026/05/today-in-ai-may-25",
        # Slug patterns
        "https://champaignmagazine.com/2026/05/24/ai-by-ai-weekly-top-5-may-18-24-2026/",
        "https://example.com/2026/05/24/weekly-roundup-ai-models",
        "https://example.com/2026/05/24/this-week-in-ai-may-22",
        "https://example.com/2026/05/24/ai-news-may-22-2026",
        "https://example.com/foo/top-10-ai-papers-of-2026",
        "https://example.com/foo/openai-recap-q1",
        "https://example.com/foo/ai-tools-updates-may-2026",
        "https://example.com/2026/05/may-recap-ai-news",
        "https://example.com/blog/monthly-digest-ai",
    ],
)
def test_is_aggregator_url_positives(url: str) -> None:
    assert _is_aggregator_url(url) is True, f"expected aggregator: {url}"


@pytest.mark.parametrize(
    "url",
    [
        # Specific articles from primary sources
        "https://blog.google/innovation-and-ai/technology/ai/google-io-2026-all-our-announcements/",
        "https://openai.com/index/gpt-5-launch",
        "https://www.anthropic.com/news/claude-4-launch",
        "https://techcrunch.com/2026/05/22/openai-files-for-ipo/",
        "https://arxiv.org/abs/2405.12345",
        # Specific articles that happen to mention numbers but aren't roundups
        "https://example.com/2026/05/22/gpt-5-scores-92-percent-on-mmlu",
        "https://example.com/2026/05/22/anthropic-raises-3-5bn",
        # Empty / None
        "",
    ],
)
def test_is_aggregator_url_negatives(url: str) -> None:
    assert _is_aggregator_url(url) is False, f"expected NOT aggregator: {url}"


# -- _parse_published_at -----------------------------------------------------


def test_parse_published_at_empty_returns_none() -> None:
    assert _parse_published_at("") is None
    assert _parse_published_at("   ") is None


def test_parse_published_at_garbage_returns_none() -> None:
    assert _parse_published_at("not-a-date") is None
    assert _parse_published_at("2026") is None


def test_parse_published_at_bare_date_is_end_of_day_utc() -> None:
    """The regression: bare dates used to parse as 00:00:00 UTC and got
    dropped by the recency grace buffer. They should parse as end-of-day."""
    dt = _parse_published_at("2026-05-19")
    assert dt is not None
    assert dt.hour == 23
    assert dt.minute == 59
    assert dt.second == 59
    assert dt.tzinfo == timezone.utc


def test_parse_published_at_full_iso_with_z_suffix() -> None:
    dt = _parse_published_at("2026-05-19T14:30:00Z")
    assert dt is not None
    assert dt == datetime(2026, 5, 19, 14, 30, 0, tzinfo=timezone.utc)


def test_parse_published_at_full_iso_with_offset() -> None:
    dt = _parse_published_at("2026-05-19T14:30:00+00:00")
    assert dt is not None
    assert dt == datetime(2026, 5, 19, 14, 30, 0, tzinfo=timezone.utc)


def test_parse_published_at_full_iso_without_tz_defaults_utc() -> None:
    dt = _parse_published_at("2026-05-19T14:30:00")
    assert dt is not None
    assert dt.tzinfo == timezone.utc


def test_bare_date_on_window_boundary_clears_grace_buffer() -> None:
    """Integration-style: confirm a bare-date item on the window boundary
    survives the (lookback + 12h) cutoff that previously dropped it."""
    lookback_hours = 168
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=lookback_hours + 12)
    # Item published on the boundary day (lookback_hours back from now).
    boundary_day = (now - timedelta(hours=lookback_hours)).strftime("%Y-%m-%d")
    parsed = _parse_published_at(boundary_day)
    assert parsed is not None
    # With the bug, parsed would be midnight UTC and fall under cutoff. With
    # the fix, parsed is end-of-day UTC and clears the cutoff.
    assert parsed >= cutoff, (
        f"boundary-day bare date should clear cutoff: parsed={parsed}, cutoff={cutoff}"
    )


# -- score_rss_items ---------------------------------------------------------


def _trend(title: str, score: float = 0.0) -> Trend:
    return Trend(
        title=title,
        url=f"https://example.com/{title.replace(' ', '-')}",
        source="RSS",
        one_line_summary=f"summary of {title}",
        why_it_matters="",
        impact_score=score,
        published_at=datetime(2026, 5, 25, tzinfo=timezone.utc),
    )


def _mock_client(content: str) -> MagicMock:
    client = MagicMock()
    client.chat.completions.create.return_value.choices = [
        MagicMock(message=MagicMock(content=content))
    ]
    return client


def test_score_rss_items_empty_returns_empty() -> None:
    client = MagicMock()
    assert score_rss_items(client, "gpt-4o", []) == []
    client.chat.completions.create.assert_not_called()


def test_score_rss_items_assigns_scores_and_wim() -> None:
    items = [_trend("A"), _trend("B")]
    payload = {
        "items": [
            {"i": 0, "impact_score": 7.5, "why_it_matters": "matters for A"},
            {"i": 1, "impact_score": 3.0, "why_it_matters": "matters for B"},
        ]
    }
    client = _mock_client(json.dumps(payload))
    scored = score_rss_items(client, "gpt-4o", items)
    by_title = {t.title: t for t in scored}
    assert by_title["A"].impact_score == 7.5
    assert by_title["A"].why_it_matters == "matters for A"
    assert by_title["B"].impact_score == 3.0
    assert by_title["B"].why_it_matters == "matters for B"


def test_score_rss_items_clamps_to_0_10() -> None:
    items = [_trend("Hyped"), _trend("Negative")]
    payload = {
        "items": [
            {"i": 0, "impact_score": 15.0, "why_it_matters": "..."},
            {"i": 1, "impact_score": -2.0, "why_it_matters": "..."},
        ]
    }
    client = _mock_client(json.dumps(payload))
    scored = score_rss_items(client, "gpt-4o", items)
    by_title = {t.title: t for t in scored}
    assert by_title["Hyped"].impact_score == 10.0
    assert by_title["Negative"].impact_score == 0.0


def test_score_rss_items_invalid_json_returns_items_unchanged() -> None:
    items = [_trend("A", score=4.0)]
    client = _mock_client("not json at all {{{")
    scored = score_rss_items(client, "gpt-4o", items)
    assert scored == items
    assert scored[0].impact_score == 4.0


def test_score_rss_items_partial_response_only_updates_known() -> None:
    items = [_trend("A"), _trend("B")]
    payload = {"items": [{"i": 0, "impact_score": 8.0, "why_it_matters": "..."}]}
    client = _mock_client(json.dumps(payload))
    scored = score_rss_items(client, "gpt-4o", items)
    by_title = {t.title: t for t in scored}
    assert by_title["A"].impact_score == 8.0
    assert by_title["B"].impact_score == 0.0  # untouched


def test_score_rss_items_handles_api_exception() -> None:
    items = [_trend("A")]
    client = MagicMock()
    client.chat.completions.create.side_effect = RuntimeError("api down")
    scored = score_rss_items(client, "gpt-4o", items)
    assert scored == items  # Items returned unmodified


def test_score_rss_items_orders_by_recency_before_scoring() -> None:
    """Newest items should be in the first 30 (the LLM-scored batch)."""
    old = _trend("Old")
    old.published_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    new = _trend("New")
    new.published_at = datetime(2026, 5, 26, tzinfo=timezone.utc)
    payload = {
        "items": [
            # i=0 is the New item (sorted first)
            {"i": 0, "impact_score": 9.0, "why_it_matters": "..."},
            {"i": 1, "impact_score": 1.0, "why_it_matters": "..."},
        ]
    }
    client = _mock_client(json.dumps(payload))
    scored = score_rss_items(client, "gpt-4o", [old, new])
    by_title = {t.title: t for t in scored}
    # New should get the high score because it's first after recency sort
    assert by_title["New"].impact_score == 9.0
    assert by_title["Old"].impact_score == 1.0
