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
    a = _t("Anthropic releases Claude 4", "https://openai.com/x", 7.0)
    rss = _t("Anthropic releases Claude 4", "https://other-coverage.com/x", 4.0)
    out = rank_and_dedupe([a], [rss], top_n=3, cross_source_boost=1.5)
    assert len(out) == 1
    # Boost added
    assert out[0].impact_score == 8.5


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
