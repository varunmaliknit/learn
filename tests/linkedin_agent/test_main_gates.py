"""Tests for the theme quality gates and Draft.trends union helper in main.py."""

from __future__ import annotations

from linkedin_agent.main import _select_publishable_themes, _themes_to_trends_union
from linkedin_agent.models import Theme, Trend


def _trend(i: int, url: str | None = None) -> Trend:
    return Trend(
        title=f"Trend {i}",
        url=url or f"https://example.com/{i}",
        source="Source",
        one_line_summary=f"Summary {i}",
        why_it_matters=f"Matters {i}",
        impact_score=7.0,
    )


def _theme(
    i: int,
    strength: float = 7.0,
    novelty: float = 5.0,
    n_supporting: int = 3,
) -> Theme:
    return Theme(
        thesis=f"Theme {i}",
        direction=f"Direction {i}",
        why_it_matters=f"Matters {i}",
        supporting=[_trend(j + i * 10) for j in range(n_supporting)],
        strength_score=strength,
        novelty_score=novelty,
    )


# ── _select_publishable_themes ────────────────────────────────────────────────

def test_select_happy_path_returns_n_themes() -> None:
    themes = [_theme(i) for i in range(3)]
    result = _select_publishable_themes(themes, num_themes=1, min_evidence=3, min_strength=6.0)
    assert result is not None
    assert len(result) == 1


def test_select_returns_none_when_too_few_themes() -> None:
    themes = [_theme(1, strength=7.0)]  # only 1, need 3
    result = _select_publishable_themes(themes, num_themes=3, min_evidence=3, min_strength=6.0)
    assert result is None


def test_select_returns_none_when_strength_below_floor() -> None:
    themes = [_theme(i, strength=4.0) for i in range(3)]
    result = _select_publishable_themes(themes, num_themes=1, min_evidence=3, min_strength=6.0)
    assert result is None


def test_select_returns_none_when_evidence_below_min() -> None:
    themes = [_theme(1, n_supporting=1)]  # only 1 data point
    result = _select_publishable_themes(themes, num_themes=1, min_evidence=3, min_strength=6.0)
    assert result is None


def test_select_trims_to_num_themes() -> None:
    themes = [_theme(i) for i in range(5)]
    result = _select_publishable_themes(themes, num_themes=2, min_evidence=3, min_strength=6.0)
    assert result is not None
    assert len(result) == 2


def test_select_mixed_quality_returns_only_strong() -> None:
    good = _theme(1, strength=8.0)
    weak = _theme(2, strength=3.0)
    themes = [good, weak]
    result = _select_publishable_themes(themes, num_themes=1, min_evidence=3, min_strength=6.0)
    assert result is not None
    assert result[0].thesis == "Theme 1"


# ── _themes_to_trends_union ───────────────────────────────────────────────────

def test_trends_union_dedupes_by_url() -> None:
    shared = _trend(99, url="https://shared.com/article")
    t1 = Theme(
        thesis="A", direction="", why_it_matters="",
        supporting=[shared, _trend(1)],
        strength_score=7.0, novelty_score=5.0,
    )
    t2 = Theme(
        thesis="B", direction="", why_it_matters="",
        supporting=[shared, _trend(2)],  # shared appears again
        strength_score=7.0, novelty_score=5.0,
    )
    union = _themes_to_trends_union([t1, t2])
    urls = [t.url for t in union]
    assert urls.count("https://shared.com/article") == 1


def test_trends_union_preserves_theme_order() -> None:
    t1 = Theme(
        thesis="A", direction="", why_it_matters="",
        supporting=[_trend(1), _trend(2)],
        strength_score=7.0, novelty_score=5.0,
    )
    t2 = Theme(
        thesis="B", direction="", why_it_matters="",
        supporting=[_trend(3), _trend(4)],
        strength_score=7.0, novelty_score=5.0,
    )
    union = _themes_to_trends_union([t1, t2])
    titles = [t.title for t in union]
    assert titles == ["Trend 1", "Trend 2", "Trend 3", "Trend 4"]
