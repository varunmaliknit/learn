"""Tests for the data models."""

from __future__ import annotations

from linkedin_agent.models import Draft, Trend


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
