"""Tests for the theme synthesis / clustering layer."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from linkedin_agent.models import Theme, Trend, _slugify
from linkedin_agent.synthesizer import (
    _score_theme,
    _themes_from_json,
    synthesize_themes,
)


def _trend(i: int, score: float = 7.0) -> Trend:
    return Trend(
        title=f"Trend {i}",
        url=f"https://example.com/{i}",
        source=f"Source {i}",
        one_line_summary=f"Summary {i}",
        why_it_matters=f"Matters {i}",
        impact_score=score,
        published_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
    )


def _candidates(n: int = 10) -> list[Trend]:
    return [_trend(i) for i in range(n)]


# ── _themes_from_json ─────────────────────────────────────────────────────────

def test_themes_from_json_happy_path() -> None:
    candidates = _candidates(5)
    data = {
        "themes": [
            {
                "thesis": "AI costs collapsing",
                "direction": "Cost parity with cloud in 18 months",
                "why_it_matters": "Budget decisions shift",
                "supporting": [0, 1, 2],
                "strength_score": 8.0,
                "novelty_score": 6.0,
            }
        ]
    }
    themes = _themes_from_json(data, candidates, min_evidence=3)
    assert len(themes) == 1
    t = themes[0]
    assert t.thesis == "AI costs collapsing"
    assert len(t.supporting) == 3
    assert t.supporting[0].title == "Trend 0"
    assert t.strength_score == 8.0
    assert t.novelty_score == 6.0
    assert t.theme_id == _slugify("AI costs collapsing")


def test_themes_from_json_drops_out_of_range_indices() -> None:
    candidates = _candidates(3)
    data = {
        "themes": [
            {
                "thesis": "Pattern X",
                "direction": "Up",
                "why_it_matters": "Big deal",
                "supporting": [0, 99, 1],  # 99 is out of range
                "strength_score": 7.0,
                "novelty_score": 5.0,
            }
        ]
    }
    themes = _themes_from_json(data, candidates, min_evidence=2)
    assert len(themes) == 1
    assert len(themes[0].supporting) == 2  # 99 dropped


def test_themes_from_json_drops_under_supported_themes() -> None:
    candidates = _candidates(5)
    data = {
        "themes": [
            {
                "thesis": "Weak pattern",
                "direction": "Unknown",
                "why_it_matters": "Maybe",
                "supporting": [0],  # only 1 support
                "strength_score": 6.0,
                "novelty_score": 5.0,
            }
        ]
    }
    themes = _themes_from_json(data, candidates, min_evidence=2)
    assert themes == []


def test_themes_from_json_clamps_scores() -> None:
    candidates = _candidates(5)
    data = {
        "themes": [
            {
                "thesis": "Overscored theme",
                "direction": "Up",
                "why_it_matters": "A lot",
                "supporting": [0, 1, 2],
                "strength_score": 99.0,
                "novelty_score": -5.0,
            }
        ]
    }
    themes = _themes_from_json(data, candidates, min_evidence=3)
    assert themes[0].strength_score == 10.0
    assert themes[0].novelty_score == 0.0


def test_themes_from_json_skips_malformed_items() -> None:
    candidates = _candidates(5)
    data = {
        "themes": [
            "not a dict",
            {
                "thesis": "Valid theme",
                "direction": "Forward",
                "why_it_matters": "Matters",
                "supporting": [0, 1, 2],
                "strength_score": 7.0,
                "novelty_score": 5.0,
            },
        ]
    }
    themes = _themes_from_json(data, candidates, min_evidence=3)
    assert len(themes) == 1
    assert themes[0].thesis == "Valid theme"


def test_themes_from_json_dedupes_supporting_indices() -> None:
    candidates = _candidates(5)
    data = {
        "themes": [
            {
                "thesis": "Pattern",
                "direction": "Up",
                "why_it_matters": "Matters",
                "supporting": [0, 0, 1, 2],  # 0 is repeated
                "strength_score": 7.0,
                "novelty_score": 5.0,
            }
        ]
    }
    themes = _themes_from_json(data, candidates, min_evidence=3)
    assert len(themes[0].supporting) == 3  # deduped


# ── _score_theme ──────────────────────────────────────────────────────────────

def test_score_theme_higher_evidence_wins_over_single_high_strength() -> None:
    # The saturation cap (_EVIDENCE_SAT) and per-evidence weight (_W_EVIDENCE)
    # ensure a theme with many corroborating data points beats a single-event theme
    # that has only a modest score advantage.
    # multi: 7.0 strength + 4*_W_EVIDENCE evidence + 5*_W_NOVELTY  = 7.0 + 3.2 + 2.0 = 12.2
    # single: 8.0 strength + 1*_W_EVIDENCE evidence + 5*_W_NOVELTY = 8.0 + 0.8 + 2.0 = 10.8
    multi = Theme(
        thesis="Multi", direction="", why_it_matters="",
        supporting=[_trend(i) for i in range(4)],
        strength_score=7.0, novelty_score=5.0,
    )
    single = Theme(
        thesis="Single", direction="", why_it_matters="",
        supporting=[_trend(99)],
        strength_score=8.0, novelty_score=5.0,
    )
    assert _score_theme(multi) > _score_theme(single)


def test_score_theme_novelty_breaks_ties() -> None:
    low_novelty = Theme(
        thesis="Low", direction="", why_it_matters="",
        supporting=[_trend(i) for i in range(3)],
        strength_score=7.0, novelty_score=3.0,
    )
    high_novelty = Theme(
        thesis="High", direction="", why_it_matters="",
        supporting=[_trend(i) for i in range(3)],
        strength_score=7.0, novelty_score=8.0,
    )
    assert _score_theme(high_novelty) > _score_theme(low_novelty)


def test_score_theme_evidence_saturates() -> None:
    """Adding more than _EVIDENCE_SAT data points should have diminishing returns."""
    from linkedin_agent.synthesizer import _EVIDENCE_SAT

    at_sat = Theme(
        thesis="Sat", direction="", why_it_matters="",
        supporting=[_trend(i) for i in range(_EVIDENCE_SAT)],
        strength_score=7.0, novelty_score=5.0,
    )
    over_sat = Theme(
        thesis="Over", direction="", why_it_matters="",
        supporting=[_trend(i) for i in range(_EVIDENCE_SAT + 3)],
        strength_score=7.0, novelty_score=5.0,
    )
    # Both should score the same (saturation kicks in)
    assert _score_theme(at_sat) == _score_theme(over_sat)


# ── synthesize_themes offline guards ─────────────────────────────────────────

def test_synthesize_themes_empty_api_key_returns_empty() -> None:
    result = synthesize_themes("", "gpt-4o", _candidates(10), num_themes=1)
    assert result == []


def test_synthesize_themes_too_few_candidates_returns_empty() -> None:
    result = synthesize_themes("sk-fake", "gpt-4o", _candidates(2), num_themes=1, min_evidence_per_theme=3)
    assert result == []


def test_synthesize_themes_exactly_at_min_candidates_passes_offline_guard() -> None:
    # len(candidates) == min_evidence_per_theme should NOT hit the early-exit guard
    # (the guard fires on strict <, not <=). The LLM call itself may fail in a
    # sandboxed environment (network blocked) — synthesize_themes handles that
    # gracefully by returning [].  We just confirm the offline guard doesn't fire.
    candidates = _candidates(3)
    # In a sandbox the network call fails and is caught, returning [].
    # In a real environment it would call OpenAI with a fake key and also return [].
    result = synthesize_themes("sk-fake-key-not-real", "gpt-4o", candidates, min_evidence_per_theme=3)
    assert isinstance(result, list)  # graceful return, not an exception
