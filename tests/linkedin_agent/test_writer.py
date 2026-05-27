"""Tests for the LinkedIn post writer prompt construction.

We don't mock the OpenAI call here — we just lock in the message-building
contract (no URL line in the trends block, no hashtag/URL instructions
leaking into the prompt) so future edits to the prompt can't silently
re-introduce the things the user explicitly asked to remove.
"""

from __future__ import annotations

from linkedin_agent.config import FormattingConfig, VoiceConfig
from linkedin_agent.models import Trend
from linkedin_agent.writer import SYSTEM_INSTRUCTIONS, _trends_block, _user_message


def _trend(i: int) -> Trend:
    return Trend(
        title=f"Trend {i}",
        url=f"https://example.com/article-{i}",
        source=f"Source {i}",
        one_line_summary=f"Summary {i}",
        why_it_matters=f"Why {i} matters",
        impact_score=7.0,
    )


def test_trends_block_does_not_render_urls() -> None:
    """Bullets must not include source URLs — the post body should be
    URL-free per user request. The block we hand to the LLM therefore
    shouldn't even surface the URLs as something to copy."""
    block = _trends_block([_trend(1), _trend(2), _trend(3)])
    assert "https://example.com" not in block
    assert "URL:" not in block
    # But the human-readable fields ARE still included so the LLM can write.
    assert "Trend 1" in block
    assert "Why 1 matters" in block


def test_user_message_forbids_urls_and_hashtags() -> None:
    """The per-message instructions handed to the LLM must explicitly
    forbid URLs and hashtags so the model can't fall back to 'safe'
    LinkedIn defaults."""
    msg = _user_message(
        trends=[_trend(1), _trend(2), _trend(3)],
        voice=VoiceConfig(),
        formatting=FormattingConfig(),
    )
    lower = msg.lower()
    # URLs and hashtags must be explicitly forbidden in the per-call message.
    assert "do not include any urls" in lower
    assert "do not include any hashtags" in lower


def test_user_message_passes_through_tight_length_target() -> None:
    """The per-call message must surface the configured length range so
    the LLM aims short (currently 600-900 chars by default)."""
    cfg = FormattingConfig(min_chars=600, max_chars=900)
    msg = _user_message(
        trends=[_trend(1), _trend(2), _trend(3)],
        voice=VoiceConfig(),
        formatting=cfg,
    )
    assert "MIN=600" in msg
    assert "MAX=900" in msg


def test_system_instructions_forbid_urls_in_body() -> None:
    """The system prompt is the layer the LLM is most likely to obey;
    keep the URL ban there too. Catches regressions where someone
    removes the rule from the system prompt but leaves it in the user
    message (or vice versa)."""
    lower = SYSTEM_INSTRUCTIONS.lower()
    assert "do not include urls" in lower or "do not include any urls" in lower
    assert "do not include hashtags" in lower or "do not include any hashtags" in lower


def test_system_instructions_drop_old_url_arrow_format() -> None:
    """The system prompt must not instruct the LLM to add '→ URL' lines
    under each bullet — that was the old format the user explicitly
    asked to remove. (The new prompt may still MENTION the pattern when
    forbidding it; we only catch instructions to USE it.)"""
    lower = SYSTEM_INSTRUCTIONS.lower()
    assert "end each bullet with the url" not in lower
    assert "all three source urls must appear" not in lower


def test_system_instructions_includes_trend_framing_rule() -> None:
    """The writer prompt must instruct the LLM to frame each bullet as a
    SIGNAL of a broader pattern, not as a single news event in isolation.
    Without this, the post reads as 'three news items' rather than
    trend analysis."""
    lower = SYSTEM_INSTRUCTIONS.lower()
    assert "trend-framing rule" in lower
    # Key concepts we want the prompt to convey to the model.
    assert "trend analysis" in lower
    assert "not news reporting" in lower
    assert "signal of" in lower or "signal of:" in lower
    assert "broader pattern" in lower


def test_system_instructions_contains_news_vs_trend_examples() -> None:
    """The prompt should contain at least one BAD/GOOD framing example
    pair so the LLM has a concrete model to imitate."""
    # Both bad and good framing examples should be present.
    text = SYSTEM_INSTRUCTIONS
    assert "BAD framing" in text
    assert "GOOD framing" in text
    # Concrete example marker from the framing section.
    assert "Coding-agent valuations" in text or "latency budgets" in text
