"""Tests for the listing-URL filter and related search helpers."""

from __future__ import annotations

import pytest

from linkedin_agent.search import _is_aggregator_url, _is_listing_url


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
