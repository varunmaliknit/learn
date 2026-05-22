"""Tests for the post-processing formatter."""

from __future__ import annotations

from linkedin_agent.config import FormattingConfig
from linkedin_agent.formatter import (
    count_required_urls,
    enforce_length,
    finalize,
    normalize_hashtags,
    strip_emoji_except_bullet,
    tidy_urls,
)


def test_strip_emoji_keeps_bullet_marker() -> None:
    text = "🔹 First bullet 🚀\n🔹 Second 💡 bullet 🤖"
    out = strip_emoji_except_bullet(text, "🔹")
    # bullet markers survive
    assert out.count("🔹") == 2
    # other emoji are gone
    for bad in ("🚀", "💡", "🤖"):
        assert bad not in out


def test_strip_emoji_no_bullet_strips_all() -> None:
    text = "Hello 🚀 world 🤖"
    out = strip_emoji_except_bullet(text, "")
    assert "🚀" not in out and "🤖" not in out


def test_strip_emoji_preserves_newlines() -> None:
    text = "🔹 Line one\n🔹 Line two\n\nFinal line"
    out = strip_emoji_except_bullet(text, "🔹")
    # Three line breaks preserved (one between bullets + blank line)
    assert out.count("\n") == 3


def test_normalize_hashtags_dedupes_and_caps() -> None:
    cfg = FormattingConfig()
    raw = ["AI", "ai", "MachineLearning", "LLM", "AIAgents", "LLM", "AIRegulation", "Robotics"]
    tags = normalize_hashtags(raw, cfg)
    assert tags[0] == "AI" and tags[1] == "MachineLearning"
    assert len(tags) <= cfg.hashtags_max
    lowered = [t.lower() for t in tags]
    assert len(lowered) == len(set(lowered))  # unique


def test_normalize_hashtags_strips_hash_prefix() -> None:
    cfg = FormattingConfig()
    tags = normalize_hashtags(["#AI", "#LLM"], cfg)
    assert all(not t.startswith("#") for t in tags)


def test_normalize_hashtags_evergreen_always_present() -> None:
    cfg = FormattingConfig()
    tags = normalize_hashtags(["SomethingElse"], cfg)
    assert "AI" in tags and "MachineLearning" in tags


def test_enforce_length_trims_at_sentence_boundary() -> None:
    body = "One short sentence. Two short sentence. Three short sentence. " * 30
    out = enforce_length(body, 200)
    assert len(out) <= 200
    # Trimmed at a sentence terminator
    assert out.rstrip().endswith(".")


def test_enforce_length_passthrough_when_short() -> None:
    body = "Hi."
    assert enforce_length(body, 1000) == body


def test_tidy_urls_strips_markdown_link_syntax() -> None:
    body = "See [the paper](https://example.com/x) for details."
    out = tidy_urls(body)
    assert "https://example.com/x" in out
    assert "[" not in out and "](" not in out


def test_count_required_urls() -> None:
    body = "https://a.com\nhttps://b.com\nhttps://c.com"
    urls = ["https://a.com", "https://b.com", "https://c.com"]
    assert count_required_urls(body, urls) == 3


def test_count_required_urls_partial() -> None:
    body = "https://a.com only"
    urls = ["https://a.com", "https://b.com", "https://c.com"]
    assert count_required_urls(body, urls) == 1


def test_finalize_full_pipeline() -> None:
    cfg = FormattingConfig(max_chars=500)
    body = (
        "Hook line 🚀.\n\nBridge line.\n\n"
        "🔹 Item one. Why it matters: it's big.\n   → https://a.com\n"
        "🔹 Item two. Why it matters: it's bigger.\n   → https://b.com\n"
        "🔹 Item three. Why it matters: biggest.\n   → https://c.com\n\n"
        "The bigger picture: connections.\n\n"
        "What would you do? 💡"
    )
    raw_tags = ["AI", "#LLM", "AIAgents"]
    clean_body, clean_tags = finalize(body, raw_tags, cfg)
    # No rogue emoji
    assert "🚀" not in clean_body and "💡" not in clean_body
    # Bullets retained
    assert clean_body.count("🔹") == 3
    # URLs retained
    assert "https://a.com" in clean_body
    # Evergreen tags present, hash prefixes stripped
    assert clean_tags[0] == "AI" and "MachineLearning" in clean_tags
    assert all(not t.startswith("#") for t in clean_tags)
