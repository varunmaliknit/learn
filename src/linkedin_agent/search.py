"""Web search for high-impact AI trends over a configurable lookback window.

Primary source: OpenAI Responses API with the built-in `web_search_preview`
tool, which returns text with inline citations. We then ask the model (without
the search tool) to coerce that into structured JSON trends.

Secondary source (best-effort): a small set of curated AI-focused RSS feeds.
Items that appear in both sources get an impact boost in the ranker.

The lookback window is controlled by ``lookback_hours`` (default 168 = 7 days
for the weekly cadence; pass 24 for daily).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import feedparser
from openai import OpenAI

from linkedin_agent.models import Trend

logger = logging.getLogger(__name__)


DEFAULT_RSS_FEEDS = [
    "https://openai.com/news/rss.xml",
    "https://www.anthropic.com/news/rss.xml",
    "https://deepmind.google/blog/rss.xml",
    "https://huggingface.co/blog/feed.xml",
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://venturebeat.com/category/ai/feed/",
    "https://the-decoder.com/feed/",
]


def _window_phrase(lookback_hours: int) -> str:
    """Human-friendly phrase for the lookback window (e.g. '24 hours', '7 days')."""
    if lookback_hours % 24 == 0 and lookback_hours >= 24:
        days = lookback_hours // 24
        return "24 hours" if days == 1 else f"{days} days"
    return f"{lookback_hours} hours"


def _web_search_prompt(now: datetime | None = None, lookback_hours: int = 168) -> str:
    now = now or datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    window_start = (now - timedelta(hours=lookback_hours)).strftime("%Y-%m-%d")
    window = _window_phrase(lookback_hours)
    return f"""\
Today's date is {today} (UTC). Search the web for the most important AI trends, \
research breakthroughs, and product launches PUBLISHED in the last {window} \
(between {window_start} and {today} UTC).

HARD RULE on recency:
- Only include items whose ORIGINAL publication date falls inside that window.
- If the original article was published earlier and only re-shared during the window, EXCLUDE it.
- If you cannot verify the publication date from the search result, EXCLUDE the item.
- Prefer the original primary source over aggregator re-coverage.

Focus on items that are:
- High-impact (major model release, large funding round, regulatory move, notable \
research result, significant safety or capability development, big product launch \
by a major lab or platform)
- Verifiable (real URLs to reputable sources — labs, major tech publications, \
official blog posts, arXiv)

Return your findings as a clear list. For each item include:
1. Title
2. Source URL
3. Source name
4. Publication date (YYYY-MM-DD format)
5. One-line factual summary (what happened)
6. Why it matters in 1-2 sentences (for an educated technical reader)

Aim for 6-10 items, ALL within the {window} window. If you cannot find 6 items \
that genuinely fit, return fewer rather than padding with older items. Rank \
them by impact — the strongest items belong at the top."""


WEB_SEARCH_PROMPT = _web_search_prompt()  # default for back-compat


def _structure_prompt(now: datetime | None = None, lookback_hours: int = 168) -> str:
    now = now or datetime.now(timezone.utc)
    window_start = (now - timedelta(hours=lookback_hours)).strftime("%Y-%m-%d")
    today = now.strftime("%Y-%m-%d")
    window = _window_phrase(lookback_hours)
    return f"""\
From the previous search results, extract the top high-impact AI items as STRICT JSON.

Only include items whose publication date is between {window_start} and {today} (UTC). \
DROP anything older even if it appeared in the search results.

Output ONLY valid JSON matching this schema, no prose:
{{
  "trends": [
    {{
      "title": "string",
      "url": "string (must be a real http(s) URL from the search results)",
      "source": "string (publication or organization name)",
      "published_at": "YYYY-MM-DD or empty if unknown",
      "one_line_summary": "string (max 120 chars, factual, no hype)",
      "why_it_matters": "string (1-2 sentences, max 240 chars)",
      "impact_score": number (0.0-10.0; 10 = once-a-year-class event)
    }}
  ]
}}

Rules:
- Include at most 10 items, ordered by impact_score descending.
- impact_score should be calibrated: 9-10 reserved for genuinely huge developments; \
6-8 for solid but routine; below 6 for marginal items.
- DROP any item whose URL you cannot cite from the search results.
- DROP any item dated before {window_start}.
- DROP duplicates / multiple articles about the same underlying event (keep the strongest source).
- STRONGLY prefer primary sources. Primary = the org/lab/paper itself: openai.com, \
anthropic.com, deepmind.google, ai.meta.com, huggingface.co, arxiv.org, nature.com, \
sec.gov filings, official company press releases, official policy / regulatory body sites.
- Aggregators (random recap blogs, content farms, generic AI roundup pages, sites \
whose URL contains tell-tale patterns like /ai-recap-/, /ai-roundup-/, \
/ai-news-may-DD-YYYY/, /weekly-ai-/) are NEVER acceptable when a primary source \
exists for the same event. If the only available source is an aggregator and the \
event is genuinely from the last {window}, you may include it BUT cap its \
impact_score at 5.0 to reflect the lower confidence.
- Reputable trade press (techcrunch.com, theverge.com, bloomberg.com, reuters.com, \
ft.com, wsj.com, theinformation.com, semianalysis.com) is acceptable as a primary source \
when the underlying event is a deal / regulatory / market move and no \
better source exists."""


STRUCTURE_PROMPT = _structure_prompt()  # default for back-compat


def _structured_trends_from_text(
    client: OpenAI,
    model: str,
    search_text: str,
    lookback_hours: int = 168,
) -> list[Trend]:
    """Second LLM pass: turn the free-form search result into JSON trends."""
    # Import locally to avoid a hard formatter↔search circular at module load.
    from linkedin_agent.formatter import _strip_tracking

    response = client.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _structure_prompt(lookback_hours=lookback_hours)},
            {"role": "user", "content": search_text},
        ],
        temperature=0.1,
    )
    raw = response.choices[0].message.content or "{}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("structure pass returned invalid JSON; trying to recover")
        data = {}

    # Recency cutoff = lookback window + 12h grace buffer (timezone noise,
    # end-of-day publishes that landed just before the window started).
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours + 12)

    trends: list[Trend] = []
    for item in data.get("trends", []):
        try:
            published_raw = str(item.get("published_at", "")).strip()
            published_at: datetime | None = None
            if published_raw:
                try:
                    published_at = datetime.strptime(published_raw, "%Y-%m-%d").replace(
                        tzinfo=timezone.utc
                    )
                except ValueError:
                    published_at = None

            # Hard recency gate: if we have a publication date and it's older
            # than (lookback_hours + 12h grace), drop the item.
            if published_at is not None and published_at < cutoff:
                logger.info(
                    "dropping trend %r as too old: published_at=%s, cutoff=%s",
                    item.get("title"),
                    published_at.isoformat(),
                    cutoff.isoformat(),
                )
                continue

            trends.append(
                Trend(
                    title=str(item["title"]).strip(),
                    url=_strip_tracking(str(item["url"]).strip()),
                    source=str(item.get("source", "")).strip(),
                    one_line_summary=str(item["one_line_summary"]).strip(),
                    why_it_matters=str(item["why_it_matters"]).strip(),
                    impact_score=float(item.get("impact_score", 0.0)),
                    published_at=published_at,
                )
            )
        except (KeyError, ValueError, TypeError):
            logger.warning("skipping malformed trend item: %r", item)
            continue
    return trends


def _openai_web_search(client: OpenAI, model: str, lookback_hours: int = 168) -> str:
    """Call the Responses API with the web_search_preview tool, return text output."""
    response = client.responses.create(
        model=model,
        tools=[{"type": "web_search_preview"}],
        input=_web_search_prompt(lookback_hours=lookback_hours),
    )
    # The Responses API returns a list of output items; `output_text` is the
    # convenience accessor for the concatenated assistant text.
    text = getattr(response, "output_text", "") or ""
    if not text:
        logger.warning("OpenAI web_search returned empty output_text")
    return text


def fetch_openai_trends(
    api_key: str,
    model: str = "gpt-4o",
    lookback_hours: int = 168,
) -> list[Trend]:
    """Fetch trends via OpenAI web search + structure pass."""
    client = OpenAI(api_key=api_key)
    search_text = _openai_web_search(client, model, lookback_hours=lookback_hours)
    if not search_text.strip():
        return []
    return _structured_trends_from_text(client, model, search_text, lookback_hours=lookback_hours)


def fetch_rss_recent(feeds: list[str], hours: int = 168) -> list[Trend]:
    """Pull recent items from RSS feeds. Returns Trends with impact_score=0 (set later)."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    items: list[Trend] = []
    for url in feeds:
        try:
            parsed = feedparser.parse(url)
        except Exception as e:  # noqa: BLE001
            logger.warning("RSS fetch failed for %s: %s", url, e)
            continue
        for entry in parsed.entries[:15]:
            try:
                published_struct = entry.get("published_parsed") or entry.get("updated_parsed")
                if published_struct is None:
                    continue
                published_at = datetime(*published_struct[:6], tzinfo=timezone.utc)
                if published_at < cutoff:
                    continue
                items.append(
                    Trend(
                        title=entry.get("title", "").strip(),
                        url=entry.get("link", "").strip(),
                        source=parsed.feed.get("title", "RSS"),
                        one_line_summary=(entry.get("summary", "") or "")[:300].strip(),
                        why_it_matters="",
                        impact_score=0.0,
                        published_at=published_at,
                    )
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("RSS entry parse failed: %s", e)
                continue
    return items


def gather_trends(
    openai_api_key: str,
    model: str = "gpt-4o",
    extra_rss_feeds: list[str] | None = None,
    lookback_hours: int = 168,
) -> dict[str, list[Trend]]:
    """Gather trends from both sources. Returns {"openai": [...], "rss": [...]}."""
    feeds = DEFAULT_RSS_FEEDS + list(extra_rss_feeds or [])
    window = _window_phrase(lookback_hours)
    openai_trends: list[Trend] = []
    rss_trends: list[Trend] = []

    if openai_api_key:
        try:
            openai_trends = fetch_openai_trends(
                openai_api_key, model, lookback_hours=lookback_hours
            )
            logger.info("OpenAI web search returned %d trends", len(openai_trends))
        except Exception as e:  # noqa: BLE001
            logger.error("OpenAI web search failed: %s", e)
    else:
        logger.warning("OPENAI_API_KEY is empty; skipping web search")

    try:
        rss_trends = fetch_rss_recent(feeds, hours=lookback_hours)
        logger.info("RSS gathered %d items in last %s", len(rss_trends), window)
    except Exception as e:  # noqa: BLE001
        logger.error("RSS gather failed: %s", e)

    return {"openai": openai_trends, "rss": rss_trends}


def _debug_dump(trends: list[Trend]) -> list[dict[str, Any]]:
    return [
        {
            "title": t.title,
            "url": t.url,
            "source": t.source,
            "impact_score": t.impact_score,
        }
        for t in trends
    ]
