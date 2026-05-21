"""OpenAI-powered news summarization and sentiment analysis."""

from __future__ import annotations

import json
import logging

from openai import OpenAI

from stock_agent.models import NewsArticle, NewsSummary, Sentiment

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a portfolio analyst preparing a daily briefing for an investor. \
Your job is to help them decide if any action is needed on this stock today.

Given news articles about a stock, provide:

1. **summary**: 2-3 sentences covering the MOST IMPORTANT developments. \
Focus on things that move stock prices: earnings results, guidance changes, \
analyst upgrades/downgrades, management changes, regulatory news, M&A activity, \
competitive developments, macro impacts. Skip generic filler articles.

2. **sentiment**: "bullish", "bearish", or "neutral" based on the overall \
news tone and likely price impact.

3. **action_needed**: true/false — ONLY set true for genuinely material events \
that could meaningfully impact the stock price or investor's position. Examples: \
earnings miss/beat by >5%, major analyst upgrade/downgrade, M&A announcement, \
CEO departure, regulatory action, dividend cut/suspension, guidance revision. \
Do NOT flag routine news, general market commentary, or minor price movements.

4. **action_reason**: If action_needed is true, one specific sentence explaining \
the material event. Be concrete (e.g., "Q1 EPS beat estimates by 15%").

5. **key_points**: 2-4 bullet points, each starting with a category tag:
   - [EARNINGS] for results, guidance, estimates
   - [ANALYST] for upgrades, downgrades, price targets
   - [CORPORATE] for M&A, management, strategy
   - [MARKET] for sector trends, macro factors
   - [RISK] for regulatory, legal, competitive threats
   - [DIVIDEND] for yield, payout changes

Respond in JSON:
{
  "summary": "...",
  "sentiment": "bullish|bearish|neutral",
  "action_needed": true|false,
  "action_reason": "...",
  "key_points": ["[TAG] point 1", "[TAG] point 2"]
}"""


def summarize_news(
    symbol: str,
    name: str,
    articles: list[NewsArticle],
    api_key: str,
) -> NewsSummary:
    if not articles:
        return NewsSummary(
            symbol=symbol,
            name=name,
            articles=[],
            ai_summary="No recent news found.",
            sentiment=Sentiment.NEUTRAL,
        )

    if not api_key:
        relevant = articles[:5]
        headlines = "\n".join(f"- {a.title}" for a in relevant)
        return NewsSummary(
            symbol=symbol,
            name=name,
            articles=relevant,
            ai_summary=f"Recent headlines:\n{headlines}",
            sentiment=Sentiment.NEUTRAL,
            key_points=[a.title for a in relevant[:3]],
        )

    article_text = "\n".join(
        f"- [{a.source}] {a.title}" for a in articles[:12]
    )
    user_prompt = f"Stock: {name} ({symbol})\n\nRecent articles:\n{article_text}"

    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=600,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content or "{}"
        parsed = json.loads(content)

        sentiment_str = parsed.get("sentiment", "neutral").lower()
        sentiment_map = {
            "bullish": Sentiment.BULLISH,
            "bearish": Sentiment.BEARISH,
            "neutral": Sentiment.NEUTRAL,
        }

        action_needed = parsed.get("action_needed", False)
        action_reason = parsed.get("action_reason", "")
        summary = parsed.get("summary", "")
        if action_needed and action_reason:
            summary = f"⚡ ACTION: {action_reason}\n\n{summary}"

        return NewsSummary(
            symbol=symbol,
            name=name,
            articles=articles,
            ai_summary=summary,
            sentiment=sentiment_map.get(sentiment_str, Sentiment.NEUTRAL),
            key_points=parsed.get("key_points", []),
        )
    except Exception:
        logger.exception("Error summarizing news for %s", symbol)
        headlines = "\n".join(f"- {a.title}" for a in articles[:5])
        return NewsSummary(
            symbol=symbol,
            name=name,
            articles=articles,
            ai_summary=f"AI summary unavailable. Recent headlines:\n{headlines}",
            sentiment=Sentiment.NEUTRAL,
            key_points=[a.title for a in articles[:3]],
        )
