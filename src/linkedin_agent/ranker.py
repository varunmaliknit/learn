"""Rank and dedupe trends across sources, then trim to top-N."""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from linkedin_agent.models import Trend
from linkedin_agent.search import CONSUMER_TECH_BLOG_HOSTS, TIER1_HOSTS

logger = logging.getLogger(__name__)


_TITLE_NORMALIZE = re.compile(r"[^a-z0-9 ]+")

# Magnitudes for the source-quality nudge applied after raw LLM scoring.
# Kept small so the LLM's impact judgement still dominates — these only
# tip ties between two equally-scored items toward the premium publisher.
TIER1_HOST_BOOST: float = 0.5
CONSUMER_BLOG_HOST_PENALTY: float = 1.0


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


def _host(u: str) -> str:
    try:
        return urlparse(u).netloc.lower().removeprefix("www.")
    except Exception:  # noqa: BLE001
        return ""


def _host_tier_adjustment(url: str) -> float:
    """Return the score nudge applied for the publisher of this URL.

    +TIER1_HOST_BOOST for premium business / analyst press and primary
    sources; -CONSUMER_BLOG_HOST_PENALTY for consumer-tech / SEO-bait
    blogs; 0 for everything else. Keeps the LLM's impact score in charge
    of overall ordering while making the top-3 pick lean toward premium
    publishers when scores are close."""
    host = _host(url)
    if not host:
        return 0.0
    # Match subdomains too: feeds.bloomberg.com → bloomberg.com.
    for tier1 in TIER1_HOSTS:
        if host == tier1 or host.endswith("." + tier1):
            return TIER1_HOST_BOOST
    for blog in CONSUMER_TECH_BLOG_HOSTS:
        if host == blog or host.endswith("." + blog):
            return -CONSUMER_BLOG_HOST_PENALTY
    return 0.0


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
        # Fresh RSS-only item. Preserve any LLM score already assigned upstream
        # (search.score_rss_items); only apply the legacy 4.0 baseline when the
        # item arrived completely unscored (impact_score==0), so we don't
        # silently inflate low-but-legitimate LLM scores (e.g. a 2.0 filler
        # item should stay at 2.0, not get bumped to 4.0).
        if r.impact_score <= 0:
            r.impact_score = 4.0
        keep.append(r)

    # Apply the publisher-tier nudge. Premium business / analyst press gets a
    # small boost; consumer-tech / SEO-bait blogs get a larger penalty. Keeps
    # the LLM's impact score in charge of the rough ordering while shifting
    # ties toward the higher-tier source.
    for k in keep:
        k.impact_score += _host_tier_adjustment(k.url)
        # Clip below by zero so a heavy consumer-blog penalty can't make
        # the score go negative (downstream UIs round-display scores).
        if k.impact_score < 0:
            k.impact_score = 0.0

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
