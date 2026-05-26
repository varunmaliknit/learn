"""Rank and dedupe trends across sources, then trim to top-N."""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from linkedin_agent.models import Trend

logger = logging.getLogger(__name__)


_TITLE_NORMALIZE = re.compile(r"[^a-z0-9 ]+")


def _normalize_title(t: str) -> str:
    return _TITLE_NORMALIZE.sub("", t.lower()).strip()


def _canonical_url(u: str) -> str:
    """Strip tracking junk and fragments for dedup comparison."""
    try:
        parsed = urlparse(u)
        host = parsed.netloc.lower().removeprefix("www.")
        path = parsed.path.rstrip("/")
        return f"{host}{path}"
    except Exception:  # noqa: BLE001
        return u


def _title_overlap_score(a: str, b: str) -> float:
    """Cheap Jaccard-on-words approximation for fuzzy title dedup."""
    aw = set(_normalize_title(a).split())
    bw = set(_normalize_title(b).split())
    if not aw or not bw:
        return 0.0
    return len(aw & bw) / len(aw | bw)


def _is_duplicate(a: Trend, b: Trend) -> bool:
    if _canonical_url(a.url) == _canonical_url(b.url):
        return True
    return _title_overlap_score(a.title, b.title) >= 0.6


def rank_and_dedupe(
    openai_trends: list[Trend],
    rss_trends: list[Trend],
    top_n: int = 3,
    cross_source_boost: float = 1.5,
) -> list[Trend]:
    """Combine, dedupe, score-boost cross-source hits, return top N by impact."""
    # Start with OpenAI-sourced trends since they already have impact scores.
    keep: list[Trend] = []
    for t in openai_trends:
        if not t.url or not t.title:
            continue
        if any(_is_duplicate(t, k) for k in keep):
            continue
        keep.append(t)

    # Add RSS items only if they aren't already covered; small base impact.
    for r in rss_trends:
        if not r.url or not r.title:
            continue
        dup_idx = next(
            (i for i, k in enumerate(keep) if _is_duplicate(r, k)),
            None,
        )
        if dup_idx is not None:
            keep[dup_idx].impact_score += cross_source_boost
            continue
        # Fresh RSS-only item: low base impact (we have no LLM judgment).
        r.impact_score = max(r.impact_score, 4.0)
        keep.append(r)

    keep.sort(key=lambda t: t.impact_score, reverse=True)

    # Diagnostic log: dump every candidate with its source and final score so we
    # can tell whether the quality-floor gate fires because no candidates exist,
    # because the LLM scored them low, or because the flat 4.0 base for
    # RSS-only items kept them under the floor.
    if keep:
        logger.info(
            "ranker pool (%d candidates, top %d returned):", len(keep), top_n
        )
        for i, t in enumerate(keep, 1):
            marker = "*" if i <= top_n else " "
            title = t.title if len(t.title) <= 80 else t.title[:77] + "..."
            logger.info(
                "  %s %2d. score=%4.1f  source=%-12s  %s  (%s)",
                marker,
                i,
                t.impact_score,
                t.source[:12],
                title,
                t.short_source(),
            )
    else:
        logger.info("ranker pool is empty after dedup")

    return keep[:top_n]
