"""Post-processing: enforce length, hashtag policy, emoji policy, and URL hygiene.

Runs AFTER the LLM draft. Hard-removes any stray emoji that isn't our bullet
marker, trims to the configured max length, and reconciles hashtags.
"""

from __future__ import annotations

import re

from linkedin_agent.config import FormattingConfig

# Common emoji ranges. We strip everything matching these EXCEPT the configured
# bullet marker (added back after stripping).
_EMOJI_RE = re.compile(
    "["
    "\U0001f300-\U0001f5ff"
    "\U0001f600-\U0001f64f"
    "\U0001f680-\U0001f6ff"
    "\U0001f700-\U0001f77f"
    "\U0001f780-\U0001f7ff"
    "\U0001f800-\U0001f8ff"
    "\U0001f900-\U0001f9ff"
    "\U0001fa00-\U0001fa6f"
    "\U0001fa70-\U0001faff"
    "\U00002600-\U000027bf"
    "]"
)


def strip_emoji_except_bullet(text: str, bullet: str) -> str:
    """Remove all emoji except the configured bullet marker."""
    placeholder = "\u0000BULLET\u0000"
    if bullet:
        text = text.replace(bullet, placeholder)
    text = _EMOJI_RE.sub("", text)
    if bullet:
        text = text.replace(placeholder, bullet)
    # Collapse runs of whitespace introduced by removed glyphs, preserving newlines.
    lines = []
    for line in text.split("\n"):
        # Collapse runs of spaces/tabs only (keep newlines intact).
        line = re.sub(r"[ \t]+", " ", line).rstrip()
        lines.append(line)
    return "\n".join(lines)


def normalize_hashtags(
    hashtags: list[str],
    formatting: FormattingConfig,
) -> list[str]:
    """Ensure evergreen tags present, no duplicates, count within bounds."""
    seen: set[str] = set()
    out: list[str] = []
    # Start with evergreen so they always come first.
    for tag in formatting.evergreen_hashtags + hashtags:
        clean = tag.strip().lstrip("#").replace(" ", "")
        if not clean:
            continue
        key = clean.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(clean)
    # Trim to max; if below min, leave as-is (model gave us what it gave us).
    return out[: formatting.hashtags_max]


def enforce_length(body: str, max_chars: int) -> str:
    """If body exceeds max_chars, trim from the end at a sentence boundary."""
    if len(body) <= max_chars:
        return body
    # Walk back to nearest sentence end inside the limit.
    cut = body[:max_chars]
    for sentinel in ["\n\n", ". ", "? ", "! "]:
        idx = cut.rfind(sentinel)
        if idx >= max_chars * 0.7:
            return cut[: idx + len(sentinel)].rstrip()
    return cut.rstrip()


def tidy_urls(body: str) -> str:
    """Strip markdown link syntax — LinkedIn shows raw URLs."""
    body = re.sub(r"\[([^\]]+)\]\((https?://[^\)]+)\)", r"\1 \2", body)
    return body


def finalize(
    body: str,
    hashtags: list[str],
    formatting: FormattingConfig,
) -> tuple[str, list[str]]:
    """Apply all post-processing. Returns (clean_body, clean_hashtags)."""
    body = tidy_urls(body)
    body = strip_emoji_except_bullet(body, formatting.bullet_marker)
    body = enforce_length(body, formatting.max_chars)
    tags = normalize_hashtags(hashtags, formatting)
    return body.strip(), tags


def count_required_urls(body: str, trend_urls: list[str]) -> int:
    """How many of the trend URLs appear in the body — used as a sanity gate."""
    return sum(1 for u in trend_urls if u and u in body)
