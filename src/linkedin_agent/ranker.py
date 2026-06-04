"""Rank and dedupe trends across sources, then trim to top-N."""

from __future__ import annotations

import logging
import math
import re
from datetime import datetime, timezone
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
    _log_pool(keep, top_n, label="rank_and_dedupe")

    return keep[:top_n]


def _log_pool(keep: list[Trend], top_n: int, label: str = "ranker") -> None:
    if keep:
        logger.info("%s pool (%d candidates, top %d returned):", label, len(keep), top_n)
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
        logger.info("%s pool is empty after dedup", label)


def _recency_decay(published_at: datetime | None, half_life_hours: float) -> float:
    """Return a score discount in [0, 2.5] based on age.

    Newer items are undiscounted; discount grows slowly with age so a strong
    but 3-week-old item can still outrank a weak fresh one.  Half-life of 336h
    (2 weeks) means a 4-week-old item loses ~2.5 points.
    """
    if published_at is None or half_life_hours <= 0:
        return 0.0
    age_hours = max(
        0.0,
        (datetime.now(timezone.utc) - published_at).total_seconds() / 3600,
    )
    # Exponential-decay: discount = 2.5 * (1 - 0.5^(age/half_life))
    decay = 2.5 * (1.0 - math.pow(0.5, age_hours / half_life_hours))
    return min(decay, 2.5)


def rank_candidates(
    openai_trends: list[Trend],
    rss_trends: list[Trend],
    top_n: int = 25,
    cross_source_boost: float = 1.5,
    recency_half_life_hours: float = 336.0,
) -> list[Trend]:
    """Like rank_and_dedupe but returns a larger ranked pool (for synthesis).

    Applies a soft recency decay so older-but-strong items surface as
    corroborating evidence while fresh items of equal raw impact rank higher.
    """
    keep: list[Trend] = []
    for t in openai_trends:
        if not t.url or not t.title:
            continue
        if any(_is_duplicate(t, k) for k in keep):
            continue
        keep.append(t)

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
        if r.impact_score <= 0:
            r.impact_score = 4.0
        keep.append(r)

    for k in keep:
        k.impact_score += _host_tier_adjustment(k.url)
        k.impact_score -= _recency_decay(k.published_at, recency_half_life_hours)
        if k.impact_score < 0:
            k.impact_score = 0.0

    keep.sort(key=lambda t: t.impact_score, reverse=True)
    _log_pool(keep, top_n, label="rank_candidates")
    return keep[:top_n]
