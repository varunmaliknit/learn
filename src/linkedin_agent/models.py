"""Data models for the LinkedIn post agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Trend:
    """A single AI trend / news item surfaced by web search."""

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
class Draft:
    """A drafted LinkedIn post + the trends that informed it."""

    draft_id: str  # e.g. "2026-05-22"
    body: str
    hashtags: list[str] = field(default_factory=list)
    trends: list[Trend] = field(default_factory=list)
    generated_at: datetime | None = None

    def full_text(self) -> str:
        """Final post text including hashtags."""
        if not self.hashtags:
            return self.body.rstrip()
        tags = " ".join(f"#{h.lstrip('#')}" for h in self.hashtags)
        return f"{self.body.rstrip()}\n\n{tags}"
