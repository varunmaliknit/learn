"""Tests for the data models."""

from __future__ import annotations

from linkedin_agent.models import Draft, Theme, Trend, _slugify


def test_trend_short_source_strips_www() -> None:
    t = Trend(
        title="x", url="https://www.openai.com/blog/x",
        source="OpenAI", one_line_summary="y", why_it_matters="z",
    )
    assert t.short_source() == "openai.com"


def test_trend_short_source_handles_paths() -> None:
    t = Trend(
        title="x", url="https://example.com/a/b/c",
        source="ex", one_line_summary="y", why_it_matters="z",
    )
    assert t.short_source() == "example.com"


def test_draft_full_text_appends_hashtags() -> None:
    d = Draft(draft_id="2026-05-22", body="Hello.", hashtags=["AI", "LLM"])
    out = d.full_text()
    assert out == "Hello.\n\n#AI #LLM"


def test_draft_full_text_no_hashtags() -> None:
    d = Draft(draft_id="2026-05-22", body="Hello.")
    assert d.full_text() == "Hello."


def test_draft_full_text_strips_leading_hash() -> None:
    d = Draft(draft_id="2026-05-22", body="Hi.", hashtags=["#AI"])
    assert d.full_text().endswith("#AI")


def test_theme_evidence_count() -> None:
    t = Trend(
        title="x", url="https://a.com", source="s",
        one_line_summary="y", why_it_matters="z",
    )
    theme = Theme(
        thesis="Test thesis",
        direction="Up",
        why_it_matters="Matters",
        supporting=[t, t],
    )
    assert theme.evidence_count == 2


def test_slugify_basic() -> None:
    assert _slugify("Inference latency is the new frontier fight") == \
        "inference-latency-is-the-new-frontier-fight"


def test_slugify_strips_special_chars() -> None:
    assert _slugify("Cost/FLOP ratios: a $500M story") == "cost-flop-ratios-a-500m-story"


def test_slugify_truncates_at_60() -> None:
    long = "a" * 80
    assert len(_slugify(long)) <= 60


def test_draft_has_themes_field() -> None:
    d = Draft(draft_id="2026-05-22", body="Body.")
    assert d.themes == []


def test_draft_trends_union_from_themes() -> None:
    """Draft.trends can be populated from themes union by the caller."""
    trend = Trend(title="T", url="https://a.com", source="s",
                  one_line_summary="y", why_it_matters="z")
    theme = Theme(thesis="P", direction="", why_it_matters="", supporting=[trend])
    d = Draft(draft_id="2026-05-22", body="B.", trends=[trend], themes=[theme])
    assert len(d.trends) == 1
    assert d.themes[0].thesis == "P"
