"""Web search for high-impact AI trends in the last 24 hours.

Primary source: OpenAI Responses API with the built-in `web_search_preview`
tool, which returns text with inline citations. We then ask the model (without
the search tool) to coerce that into structured JSON trends.

Secondary source (best-effort): a small set of curated AI-focused RSS feeds.
Items that appear in both sources get an impact boost in the ranker.
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


WEB_SEARCH_PROMPT = """\
Search the web for the most important AI news, research, and product announcements \
from the last 24 hours.

Focus on items that are:
- High-impact (large model release, major funding, regulatory move, notable research result, \
significant safety or capability development, big product launch by a major lab)
- Time-sensitive (genuinely from the last ~24 hours, not older recycled coverage)
- Verifiable (real URLs to reputable sources — labs, major tech publications, papers)

Return your findings as a clear list with for each item:
1. Title
2. Source URL
3. Source name
4. One-line factual summary (what happened)
5. Why it matters in 1-2 sentences (for an educated technical reader)

Aim for 5-8 items. Skip anything older than 36 hours."""


STRUCTURE_PROMPT = """\
From the previous search results, extract the top high-impact AI items as STRICT JSON.

Output ONLY valid JSON matching this schema, no prose:
{
  "trends": [
    {
      "title": "string",
      "url": "string (must be a real http(s) URL from the search results)",
      "source": "string (publication or organization name)",
      "one_line_summary": "string (max 120 chars, factual, no hype)",
      "why_it_matters": "string (1-2 sentences, max 240 chars)",
      "impact_score": number (0.0-10.0; 10 = once-a-year-class news)
    }
  ]
}

Rules:
- Include at most 8 items, ordered by impact_score descending.
- impact_score should be calibrated: 9-10 reserved for genuinely huge news; \
6-8 for solid but routine; below 6 for marginal items.
- DROP any item whose URL you cannot cite from the search results.
- DROP duplicates / multiple articles about the same underlying event (keep the strongest source).
- Prefer primary sources (lab blogs, papers) over aggregator coverage."""


def _structured_trends_from_text(client: OpenAI, model: str, search_text: str) -> list[Trend]:
    """Second LLM pass: turn the free-form search result into JSON trends."""
    response = client.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": STRUCTURE_PROMPT},
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

    trends: list[Trend] = []
    for item in data.get("trends", []):
        try:
            trends.append(
                Trend(
                    title=str(item["title"]).strip(),
                    url=str(item["url"]).strip(),
                    source=str(item.get("source", "")).strip(),
                    one_line_summary=str(item["one_line_summary"]).strip(),
                    why_it_matters=str(item["why_it_matters"]).strip(),
                    impact_score=float(item.get("impact_score", 0.0)),
                )
            )
        except (KeyError, ValueError, TypeError):
            logger.warning("skipping malformed trend item: %r", item)
            continue
    return trends


def _openai_web_search(client: OpenAI, model: str) -> str:
    """Call the Responses API with the web_search_preview tool, return text output."""
    response = client.responses.create(
        model=model,
        tools=[{"type": "web_search_preview"}],
        input=WEB_SEARCH_PROMPT,
    )
    # The Responses API returns a list of output items; `output_text` is the
    # convenience accessor for the concatenated assistant text.
    text = getattr(response, "output_text", "") or ""
    if not text:
        logger.warning("OpenAI web_search returned empty output_text")
    return text


def fetch_openai_trends(api_key: str, model: str = "gpt-4o") -> list[Trend]:
    """Fetch trends via OpenAI web search + structure pass."""
    client = OpenAI(api_key=api_key)
    search_text = _openai_web_search(client, model)
    if not search_text.strip():
        return []
    return _structured_trends_from_text(client, model, search_text)


def fetch_rss_recent(feeds: list[str], hours: int = 24) -> list[Trend]:
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
) -> dict[str, list[Trend]]:
    """Gather trends from both sources. Returns {"openai": [...], "rss": [...]}."""
    feeds = DEFAULT_RSS_FEEDS + list(extra_rss_feeds or [])
    openai_trends: list[Trend] = []
    rss_trends: list[Trend] = []

    if openai_api_key:
        try:
            openai_trends = fetch_openai_trends(openai_api_key, model)
            logger.info("OpenAI web search returned %d trends", len(openai_trends))
        except Exception as e:  # noqa: BLE001
            logger.error("OpenAI web search failed: %s", e)
    else:
        logger.warning("OPENAI_API_KEY is empty; skipping web search")

    try:
        rss_trends = fetch_rss_recent(feeds)
        logger.info("RSS gathered %d items in last 24h", len(rss_trends))
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
