"""Data models for the LinkedIn post agent."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Trend:
    """A single high-impact AI trend surfaced by web search or RSS."""

    title: str
    url: str
    source: str
    one_line_summary: str
    why_it_matters: str
    impact_score: float = 0.0  # 0-10 scale
    published_at: datetime | None = None

    def short_source(self) -> str:
        """Domain-only source for compact rendering."""
        from urllib.parse import urlparse

        host = urlparse(self.url).netloc
        return host.removeprefix("www.")


@dataclass
class Theme:
    """A named trend-pattern backed by multiple corroborating Trend data points."""

    thesis: str          # e.g. "Inference latency is the new frontier model fight"
    direction: str       # where the pattern is heading
    why_it_matters: str  # aggregate practitioner consequence
    supporting: list[Trend] = field(default_factory=list)  # 2-4 concrete events
    strength_score: float = 0.0   # aggregate pattern strength, 0-10
    novelty_score: float = 0.0    # non-obviousness / contrarian angle, 0-10
    theme_id: str = ""            # URL-safe slug, for grouping in issue/email

    @property
    def evidence_count(self) -> int:
        return len(self.supporting)


def _slugify(text: str) -> str:
    """Convert a thesis string to a short URL-safe slug."""
    slug = text.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug[:60]


@dataclass
class Draft:
    """A drafted LinkedIn post + the trends/themes that informed it."""

    draft_id: str  # e.g. "2026-05-22"
    body: str
    hashtags: list[str] = field(default_factory=list)
    trends: list[Trend] = field(default_factory=list)  # deduped union of theme supports
    themes: list[Theme] = field(default_factory=list)
    generated_at: datetime | None = None

    def full_text(self) -> str:
        """Final post text including hashtags."""
        if not self.hashtags:
            return self.body.rstrip()
        tags = " ".join(f"#{h.lstrip('#')}" for h in self.hashtags)
        return f"{self.body.rstrip()}\n\n{tags}"
