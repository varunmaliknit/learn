"""OpenAI-powered news summarization and sentiment analysis."""

from __future__ import annotations

import json
import logging

from openai import OpenAI

from stock_agent.models import NewsArticle, NewsSummary, Sentiment

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a financial news analyst. \
Given a list of news articles about a stock, provide:
1. A concise summary (2-3 sentences) of the most important developments
2. Overall sentiment: bullish, bearish, or neutral
3. Key points (3-5 bullet points)

Respond in JSON format:
{
  "summary": "...",
  "sentiment": "bullish|bearish|neutral",
  "key_points": ["point 1", "point 2", ...]
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
        headlines = "\n".join(f"- {a.title}" for a in articles[:10])
        return NewsSummary(
            symbol=symbol,
            name=name,
            articles=articles,
            ai_summary=f"Recent headlines:\n{headlines}",
            sentiment=Sentiment.NEUTRAL,
            key_points=[a.title for a in articles[:5]],
        )

    article_text = "\n".join(
        f"- [{a.source}] {a.title}" for a in articles[:15]
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
            max_tokens=500,
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

        return NewsSummary(
            symbol=symbol,
            name=name,
            articles=articles,
            ai_summary=parsed.get("summary", ""),
            sentiment=sentiment_map.get(sentiment_str, Sentiment.NEUTRAL),
            key_points=parsed.get("key_points", []),
        )
    except Exception:
        logger.exception("Error summarizing news for %s", symbol)
        headlines = "\n".join(f"- {a.title}" for a in articles[:10])
        return NewsSummary(
            symbol=symbol,
            name=name,
            articles=articles,
            ai_summary=f"AI summary unavailable. Recent headlines:\n{headlines}",
            sentiment=Sentiment.NEUTRAL,
            key_points=[a.title for a in articles[:5]],
        )
