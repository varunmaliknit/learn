"""LLM-based LinkedIn post writer.

Drafts a post that matches the user's voice samples and adheres to the
formatting policy (bullets-as-emoji only, no other emoji; tight length;
3 bullets; hashtags at the end).
"""

from __future__ import annotations

import json
import logging

from openai import OpenAI

from linkedin_agent.config import FormattingConfig, VoiceConfig
from linkedin_agent.models import Trend

logger = logging.getLogger(__name__)


def _voice_block(voice: VoiceConfig) -> str:
    parts = [
        "VOICE / PERSONA:",
        voice.persona.strip(),
    ]
    if voice.sample_posts:
        parts.append("")
        parts.append("VOICE SAMPLES — match this tone, structure, and pacing:")
        for i, sample in enumerate(voice.sample_posts, 1):
            parts.append(f"\n--- Sample {i} ---\n{sample.strip()}\n--- End sample {i} ---")
    if voice.avoid_phrases:
        parts.append("")
        parts.append("AVOID these phrases / patterns (sound generic or AI-slop):")
        for p in voice.avoid_phrases:
            parts.append(f"- {p}")
    return "\n".join(parts)


def _trends_block(trends: list[Trend]) -> str:
    out = ["TRENDS TO COVER (in order, you may rephrase but keep all 3 URLs):"]
    for i, t in enumerate(trends, 1):
        out.append(
            f"{i}. {t.title}\n"
            f"   URL: {t.url}\n"
            f"   Source: {t.source}\n"
            f"   What happened: {t.one_line_summary}\n"
            f"   Why it matters: {t.why_it_matters}"
        )
    return "\n".join(out)


SYSTEM_INSTRUCTIONS = """\
You are a LinkedIn ghostwriter for an experienced AI practitioner. \
Output ONE LinkedIn post that follows these rules EXACTLY.

STRUCTURE (this exact order):
1. A 1-2 line HOOK that signals stakes or a counterintuitive angle. No emoji in the hook.
2. A single bridge line connecting the hook to today's items.
3. Exactly THREE bullets, one per trend, in the order given. Each bullet starts with the \
bullet marker the user has set (e.g. 🔹), then the trend in one short sentence followed by \
"Why it matters:" and one tight clause. End each bullet with the URL on its own indented line \
prefixed by an arrow, e.g. "   → https://...".
4. A "The bigger picture:" line of 1-2 short sentences synthesizing what these mean together.
5. A CTA — a genuine, specific question that invites a real reply (not "Thoughts? 👇").

FORMATTING RULES (STRICT):
- The bullet marker (🔹 by default) is the ONLY emoji allowed in the entire post. \
No other emoji anywhere. No emoji in headers, hook, bigger picture, or CTA.
- Do NOT include hashtags. They will be appended separately.
- Use plain prose. No bold, no italics, no markdown headings — LinkedIn renders none of that.
- Use straight arrows " → " for URLs. Don't use markdown link syntax; LinkedIn shows the bare URL.
- All three source URLs must appear, each on its own line under its bullet.
- Body length target: between MIN and MAX characters (post text only, hashtags excluded).
- No clickbait. No phrases like "game changer", "revolutionize", "fast-paced world".
- No "I'm thrilled / excited to share". Skip filler openers.
- Use simple, direct sentences. Vary length. No bureaucratic adverbs.

CONSTRAINTS:
- You MUST use all THREE provided trends and all THREE provided URLs (one per bullet).
- Do NOT invent facts beyond what's in the trend summaries.
- Do NOT claim opinions/positions the user hasn't expressed; stay neutral-curious.

OUTPUT FORMAT (STRICT JSON, no surrounding prose):
{
  "body": "the full post text following the structure above",
  "hashtags": ["AI", "MachineLearning", "...up to 6 total..."]
}

For hashtags: 4-6 total, no leading '#'. Always include the evergreen tags provided. \
Add 2-3 specific tags relevant to the trends (e.g. LLM, AIAgents, OpenSourceAI, AIRegulation, \
AISafety, Robotics, ComputerVision). Camel-case multi-word tags (no spaces, no underscores)."""


def _user_message(
    trends: list[Trend],
    voice: VoiceConfig,
    formatting: FormattingConfig,
) -> str:
    return "\n\n".join(
        [
            _voice_block(voice),
            f"BULLET MARKER: {formatting.bullet_marker}",
            f"LENGTH (post body only, hashtags excluded): MIN={formatting.min_chars}, "
            f"MAX={formatting.max_chars} characters.",
            f"HASHTAGS: include exactly {formatting.evergreen_hashtags} as evergreen, "
            f"plus {formatting.hashtags_min - len(formatting.evergreen_hashtags)}–"
            f"{formatting.hashtags_max - len(formatting.evergreen_hashtags)} specific tags. "
            f"No leading '#'. CamelCase multi-word tags.",
            _trends_block(trends),
            "Now write the post and return the JSON.",
        ]
    )


def draft_post(
    api_key: str,
    model: str,
    trends: list[Trend],
    voice: VoiceConfig,
    formatting: FormattingConfig,
) -> tuple[str, list[str]]:
    """Call the LLM to draft a post. Returns (body, hashtags)."""
    if len(trends) < 3:
        raise ValueError(f"draft_post requires exactly 3 trends, got {len(trends)}")

    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        temperature=0.7,
        messages=[
            {"role": "system", "content": SYSTEM_INSTRUCTIONS},
            {"role": "user", "content": _user_message(trends[:3], voice, formatting)},
        ],
    )
    raw = response.choices[0].message.content or "{}"
    data = json.loads(raw)
    body = str(data.get("body", "")).strip()
    hashtags = [str(h).lstrip("#").strip() for h in data.get("hashtags", []) if str(h).strip()]
    if not body:
        raise RuntimeError("LLM returned empty post body")
    return body, hashtags
