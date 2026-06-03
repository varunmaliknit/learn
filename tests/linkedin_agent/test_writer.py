"""Tests for the LinkedIn post writer prompt construction.

We lock in the message-building contract (no URLs in themes block, no
hashtag/URL instructions leaking into the prompt) and key system-prompt
invariants so future edits can't silently reintroduce what the user
explicitly asked to remove.
"""

from __future__ import annotations

from linkedin_agent.config import FormattingConfig, VoiceConfig
from linkedin_agent.models import Theme, Trend
from linkedin_agent.writer import (
    SYSTEM_INSTRUCTIONS_MULTI,
    SYSTEM_INSTRUCTIONS_SINGLE,
    _themes_block,
    _user_message,
)


def _trend(i: int) -> Trend:
    return Trend(
        title=f"Trend {i}",
        url=f"https://example.com/article-{i}",
        source=f"Source {i}",
        one_line_summary=f"Summary {i}",
        why_it_matters=f"Why {i} matters",
        impact_score=7.0,
    )


def _theme(i: int, n_supporting: int = 3) -> Theme:
    return Theme(
        thesis=f"Theme {i} thesis",
        direction=f"Direction {i}",
        why_it_matters=f"Why theme {i} matters",
        supporting=[_trend(j + (i * 10)) for j in range(n_supporting)],
        strength_score=7.0,
        novelty_score=6.0,
    )


def test_themes_block_does_not_render_urls() -> None:
    """The themes block passed to the LLM must not surface source URLs —
    the post body must be URL-free per user request."""
    block = _themes_block([_theme(1)])
    assert "https://example.com" not in block
    # But human-readable fields ARE included so the LLM can write.
    assert "Theme 1 thesis" in block
    assert "Why" in block


def test_themes_block_includes_supporting_evidence() -> None:
    """Each supporting trend's specifics should appear in the block so the
    writer can cite them without hallucinating."""
    t = _theme(1, n_supporting=3)
    block = _themes_block([t])
    assert "Trend 10" in block  # first supporting title
    assert "Summary 10" in block
    assert "3 data points" in block


def test_user_message_forbids_urls_and_hashtags() -> None:
    """The per-message instructions must explicitly forbid URLs and
    hashtags so the model can't fall back to 'safe' LinkedIn defaults."""
    msg = _user_message(
        themes=[_theme(1)],
        voice=VoiceConfig(),
        formatting=FormattingConfig(),
        num_themes=1,
    )
    lower = msg.lower()
    assert "do not include any urls" in lower
    assert "do not include any hashtags" in lower


def test_user_message_passes_through_length_target() -> None:
    """The per-call message must surface the configured length range."""
    cfg = FormattingConfig(min_chars=700, max_chars=1100)
    msg = _user_message(
        themes=[_theme(1)],
        voice=VoiceConfig(),
        formatting=cfg,
        num_themes=1,
    )
    assert "MIN=700" in msg
    assert "MAX=1100" in msg


def test_system_instructions_single_forbid_urls() -> None:
    lower = SYSTEM_INSTRUCTIONS_SINGLE.lower()
    assert "do not include urls" in lower or "do not include any urls" in lower
    assert "do not include hashtags" in lower or "do not include any hashtags" in lower


def test_system_instructions_single_evidence_rule() -> None:
    """The single-theme prompt must instruct the LLM to write FROM the
    provided evidence, not to invent a connection."""
    lower = SYSTEM_INSTRUCTIONS_SINGLE.lower()
    assert "evidence rule" in lower
    assert "do not invent" in lower


def test_system_instructions_single_timeframe_rule() -> None:
    lower = SYSTEM_INSTRUCTIONS_SINGLE.lower()
    assert "timeframe rule" in lower
    assert "this week" in lower  # it's listed as forbidden


def test_system_instructions_single_specificity_rule() -> None:
    lower = SYSTEM_INSTRUCTIONS_SINGLE.lower()
    assert "specificity rule" in lower


def test_system_instructions_single_self_check() -> None:
    """The self-check list of banned phrases must be present."""
    assert "SELF-CHECK" in SYSTEM_INSTRUCTIONS_SINGLE
    assert "potentially" in SYSTEM_INSTRUCTIONS_SINGLE


def test_system_instructions_multi_forbid_urls() -> None:
    lower = SYSTEM_INSTRUCTIONS_MULTI.lower()
    assert "do not include urls" in lower or "no urls" in lower
    assert "no hashtags" in lower or "do not include" in lower


def test_system_instructions_multi_has_evidence_rule() -> None:
    lower = SYSTEM_INSTRUCTIONS_MULTI.lower()
    assert "evidence rule" in lower
    assert "do not invent" in lower
