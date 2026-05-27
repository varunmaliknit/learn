"""Tests for the trend ranker / deduper."""

from __future__ import annotations

from linkedin_agent.models import Trend
from linkedin_agent.ranker import rank_and_dedupe


def _t(title: str, url: str, score: float = 7.0, source: str = "Source") -> Trend:
    return Trend(
        title=title,
        url=url,
        source=source,
        one_line_summary=title,
        why_it_matters="because",
        impact_score=score,
    )


def test_rank_orders_by_impact_descending() -> None:
    a = _t("a", "https://a.com/1", 8.5)
    b = _t("b", "https://b.com/1", 9.0)
    c = _t("c", "https://c.com/1", 7.0)
    out = rank_and_dedupe([a, b, c], [], top_n=3)
    assert [x.title for x in out] == ["b", "a", "c"]


def test_dedupes_exact_url_collisions() -> None:
    a1 = _t("OpenAI launches new model", "https://openai.com/x", 9.0)
    a2 = _t("OpenAI launches new model — coverage", "https://openai.com/x", 7.0)
    b = _t("Other thing", "https://other.com/y", 8.0)
    out = rank_and_dedupe([a1, a2, b], [], top_n=3)
    assert len(out) == 2
    urls = [t.url for t in out]
    assert "https://openai.com/x" in urls
    assert "https://other.com/y" in urls


def test_dedupes_fuzzy_titles() -> None:
    a = _t(
        "Anthropic releases Claude 4 with new reasoning capabilities",
        "https://anthropic.com/claude4",
        9.0,
    )
    b = _t(
        "Anthropic releases Claude 4 new reasoning capabilities",
        "https://other.com/claude4-coverage",
        7.5,
    )
    out = rank_and_dedupe([a, b], [], top_n=3)
    assert len(out) == 1
    assert out[0].url == "https://anthropic.com/claude4"


def test_cross_source_boost_when_rss_confirms() -> None:
    # Titles need ≥0.6 Jaccard overlap to be detected as the same story.
    # Use neutral hosts (not Tier-1, not consumer-blog) so this test exercises
    # ONLY the cross-source boost, not the publisher-tier adjustment.
    a = _t("Anthropic releases Claude 4", "https://neutral-a.example/x", 7.0)
    rss = _t("Anthropic releases Claude 4", "https://neutral-b.example/x", 4.0)
    out = rank_and_dedupe([a], [rss], top_n=3, cross_source_boost=1.5)
    assert len(out) == 1
    # Boost added
    assert out[0].impact_score == 8.5


def test_tier1_host_gets_score_boost() -> None:
    """Items from premium business / analyst press get +0.5 added after
    LLM scoring so they edge out same-score Tier-2 / consumer items."""
    a = _t("AI funding round", "https://www.bloomberg.com/news/articles/foo", 7.0)
    b = _t("Different story", "https://neutral.example/x", 7.0)
    out = rank_and_dedupe([a, b], [], top_n=3)
    bloomberg = next(t for t in out if "bloomberg" in t.url)
    neutral = next(t for t in out if "neutral.example" in t.url)
    assert bloomberg.impact_score == 7.5
    assert neutral.impact_score == 7.0
    # Bloomberg should win the top-1 slot.
    assert out[0].url.endswith("/foo")


def test_consumer_blog_host_gets_score_penalty() -> None:
    """Items from consumer-tech / SEO-bait blogs get a 1.0 penalty so they
    fall behind same-score Tier-1 / neutral items in the top-3 pick."""
    a = _t("AI thing", "https://www.tomsguide.com/news/ai-thing", 7.0)
    b = _t("Different story", "https://neutral.example/x", 6.5)
    out = rank_and_dedupe([a, b], [], top_n=3)
    toms = next(t for t in out if "tomsguide" in t.url)
    neutral = next(t for t in out if "neutral.example" in t.url)
    assert toms.impact_score == 6.0  # 7.0 - 1.0
    assert neutral.impact_score == 6.5
    # The neutral item wins despite starting at a lower LLM score.
    assert "neutral.example" in out[0].url


def test_tier1_boost_handles_subdomains() -> None:
    """Subdomains of Tier-1 hosts (e.g. feeds.bloomberg.com) also get
    the boost — the matcher is suffix-aware."""
    a = _t("A", "https://feeds.bloomberg.com/technology/news/foo", 6.0)
    b = _t("B", "https://neutral.example/y", 6.0)
    out = rank_and_dedupe([a, b], [], top_n=3)
    bloomberg = next(t for t in out if "bloomberg" in t.url)
    assert bloomberg.impact_score == 6.5


def test_consumer_penalty_does_not_drive_score_below_zero() -> None:
    """If a consumer-blog item has a very low LLM score, the 1.0 penalty
    should not push impact_score negative (downstream rounding / display)."""
    a = _t("Filler", "https://www.tomsguide.com/news/foo", 0.5)
    out = rank_and_dedupe([a], [], top_n=3)
    assert out[0].impact_score == 0.0


def test_rss_only_item_added_with_floor_score() -> None:
    a = _t("Big news", "https://openai.com/x", 9.0)
    rss_only = _t("Unrelated event", "https://other.com/y", 0.0)
    out = rank_and_dedupe([a], [rss_only], top_n=3)
    assert len(out) == 2
    # Unscored RSS items (impact_score==0) get a 4.0 baseline as a safety net.
    rss_in_out = next(t for t in out if t.url == "https://other.com/y")
    assert rss_in_out.impact_score == 4.0


def test_rss_item_preserves_existing_llm_score() -> None:
    """RSS items that arrive with a non-zero score (LLM-scored by
    score_rss_items upstream) must NOT get bumped to the 4.0 baseline."""
    a = _t("Big news", "https://openai.com/x", 9.0)
    rss_low = _t("Low signal", "https://other.com/y", 2.0)
    rss_high = _t("High signal", "https://third.com/z", 7.5)
    out = rank_and_dedupe([a], [rss_low, rss_high], top_n=3)
    by_url = {t.url: t for t in out}
    assert by_url["https://other.com/y"].impact_score == 2.0
    assert by_url["https://third.com/z"].impact_score == 7.5


def test_top_n_caps_results() -> None:
    trends = [_t(f"t{i}", f"https://e.com/{i}", 5.0 + i) for i in range(10)]
    out = rank_and_dedupe(trends, [], top_n=3)
    assert len(out) == 3


def test_url_canonicalization_treats_trailing_slash_as_same() -> None:
    a = _t("Same", "https://x.com/post", 9.0)
    b = _t("Same", "https://www.x.com/post/", 7.0)
    out = rank_and_dedupe([a, b], [], top_n=3)
    assert len(out) == 1
