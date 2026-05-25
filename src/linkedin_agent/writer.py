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
2. A single bridge line connecting the hook to the bullets. Do NOT anchor it in time — see \
the TIMEFRAME RULE below.
3. Exactly THREE bullets, one per trend, in the order given. Each bullet starts with the \
bullet marker the user has set (e.g. 🔹), then ONE concrete sentence naming the specific \
event (see SPECIFICITY RULE below), followed by "Why it matters:" and one tight clause. \
End each bullet with the URL on its own indented line prefixed by an arrow, e.g. \
"   → https://...".
4. A "The bigger picture:" line of 1-2 short sentences synthesizing what these trends mean \
together — a pattern observation, not a timeframe summary.
5. A CTA — see the CTA section below.

TIMEFRAME RULE (CRITICAL):
- Do NOT mention how often you post or the time window of the trends. No "this week", \
"today", "recently", "in the last few days", "lately", "this month", "in recent days", \
"the past week", "just dropped", "breaking", "latest".
- Do NOT use the word "news" anywhere. These are TRENDS / DEVELOPMENTS / MOVES, not news.
- The post should read as evergreen high-impact AI trends — the reader doesn't need to know \
when these happened or how often you post, only that they're current and worth attention.

SPECIFICITY RULE (CRITICAL):
- Every bullet's first sentence MUST name the specific event in concrete terms: a product \
name, model name, paper finding, dollar amount, named regulation, benchmark result, named \
capability, or org-vs-org move. Generic descriptions are forbidden.
- BAD bullet first sentences (do NOT write anything like these): \
"X announced advancements in its AI-driven security solutions." \
"X enhances its AI portfolio with new capabilities." \
"X is investing in AI to improve customer experience." \
"X is exploring new frontiers in AI." These name no specific thing.
- GOOD bullet first sentences: \
"OpenAI shipped GPT-5o-mini at $0.15 per million input tokens — 5x cheaper than 4o-mini." \
"Anthropic raised $3.5bn at a $61.5bn valuation led by Lightspeed." \
"DeepMind's Gemini 3 Pro passed MMLU at 92.0%, leapfrogging Claude 3.5 Sonnet." \
"The EU AI Act's GPAI provisions took effect, requiring training-data summaries from \
model providers above 10^25 FLOPs."
- If the trend you're given lacks a concrete detail, USE WHAT IS IN THE PROVIDED "What \
happened" / "Why it matters" fields verbatim or near-verbatim. Do NOT invent details, but \
also do not hand-wave when specifics were supplied. If the supplied detail is itself \
generic, you may write a tighter version of it, but never substitute marketing-speak.

FORMATTING RULES (STRICT):
- The bullet marker (🔹 by default) is the ONLY emoji allowed in the entire post. \
No other emoji anywhere. No emoji in headers, hook, bigger picture, or CTA.
- Do NOT include hashtags. They will be appended separately.
- Use plain prose. No bold, no italics, no markdown headings — LinkedIn renders none of that.
- Use straight arrows " → " for URLs. Don't use markdown link syntax; LinkedIn shows the bare URL.
- All three source URLs must appear, each on its own line under its bullet.
- Body length target: between MIN and MAX characters (post text only, hashtags excluded).

VOICE RULES (CRITICAL — the user is picky about this):
- Write in CONCRETE language, not analyst-speak. Match the user's voice samples closely.
- BANNED stock phrases (do NOT use any of these or close variants): "game changer", \
"revolutionize", "reshape the landscape" / "reshape the playing field" / \
"reshape the field" / "reshaping the X playing field", "reshaping ... dynamics", \
"transform the industry", "unlock new possibilities", "unlock value", \
"shifting paradigms", "paving the way", "in today's fast-paced world", \
"democratize AI" / "democratize access to AI" / "democratize anything", \
"leveraging" or "leverage" (use "use"), "empower" / "empowering", \
"accelerate" when meaning faster (use "speed up"), "strategic", "synergy", \
"ecosystem" (use "market" or "stack" or be specific), "poised to", \
"in the AI landscape" / "AI landscape", "stirring up competition", "thoughts? 👇", \
"I'm thrilled", "I'm excited", "without breaking the bank", "on the horizon", \
"a fascinating time", "push boundaries", "next frontier", "uncharted territory", \
"jaw-dropping", "staggering" (use the number), "connect the dots", "raising the bar", \
"playing field", "weaving itself", "deeper into our lives", "buzzing", "seamlessly", \
"merging digital and physical worlds", "redefining how we interact".
- BANNED bureaucratic verbs: utilize, facilitate, enable (the abstract sense), incentivize, \
operationalize, optimize (unless literal), enhance (use "improve"), drive (as in "drives growth").
- BANNED hedging adverbs: "potentially", "significantly" (unless quantified), "likely", \
"increasingly", "substantially". Cut them or replace with a concrete number / example.
- For each bullet's "Why it matters:" clause: state ONE concrete consequence (a specific \
use-case, a specific number, a specific competitor, a specific technical implication). \
Do NOT say something is "important", "underscores", "highlights", "could solidify", \
"might catalyze", or "may reshape" — these are filler. Say WHAT changes for whom, in \
plain words.

"WHY IT MATTERS" EXAMPLES — study these patterns carefully:

BAD: "Why it matters: this reshapes AI hardware dynamics."
GOOD: "Why it matters: teams buying H100s now have a second supplier to play against on price."

BAD: "Why it matters: this highlights AI's expanding role in enterprise environments."
GOOD: "Why it matters: if you're picking a coding agent for your team this quarter, Codex \
just became harder to argue against in a procurement review."

BAD: "Why it matters: it could solidify the company's foothold in the market."
GOOD: "Why it matters: a 70% cheaper inference tier means use-cases that didn't pencil out \
six months ago (per-customer document analysis, real-time speech eval, agent loops with \
hundreds of tool calls) suddenly do."

BAD: "Why it matters: this initiative might catalyze AI-driven environmental solutions."
GOOD: "Why it matters: APAC-based teams working on climate problems get a no-equity \
funding path with DeepMind compute attached — rare combination."

BAD: "Why it matters: it could potentially reshape investment landscapes."
GOOD: "Why it matters: an OpenAI IPO at this scale gives every AI-native startup a new \
comp benchmark when raising — and a public price for AI optimism that VCs can mark to."

The pattern: concrete actor + concrete consequence + (when possible) a specific number, \
competitor, decision, or use-case. Never two sentences of analysis. One tight sentence.

- Prefer SHORT punchy sentences over long ones. Vary length. If a sentence has three commas, \
break it up.
- First-person but NOT self-promotional. Do not say "in my experience" or "I've seen" unless \
the trend summaries genuinely support it. Stay neutral-curious.

CTA RULES:
- The CTA must be a SPECIFIC question grounded in the trends you just covered. \
It should reference what someone reading this would actually have to decide, build, or test.
- BAD CTA (too generic, do NOT write this): "What do you think these shifts mean for the AI \
tools and services we rely on every day?"
- BAD CTA (too generic): "Curious to hear your thoughts on this."
- GOOD CTA shape: "For [specific role / type of builder]: which of these [forces you to / \
opens up / kills] [specific decision], and what does it replace in your current stack?"
- GOOD CTA shape: "Do you spot a gap I'm missing in [one of the items], or a counter-take I \
should consider?"
- Keep the CTA to ONE question, max two sentences. Do not stack multiple questions.

CONSTRAINTS:
- You MUST use all THREE provided trends and all THREE provided URLs (one per bullet).
- Do NOT invent facts beyond what's in the trend summaries.
- Do NOT claim opinions/positions the user hasn't expressed; stay neutral-curious.

SELF-CHECK BEFORE RETURNING JSON:
After drafting the post, scan your "body" text. If it contains ANY of these words/phrases, \
rewrite that sentence before returning:
  - "potentially", "could solidify", "could revolutionize", "could change the game", \
"might catalyze", "might find", "may reshape", "may alter", "may influence", \
"likely to", "increasingly", "substantially", "significantly" (unless followed by a number), \
"highlights", "underscores", "stirring up", "game changer", "game-changer", "reshape", \
"reshaping", "transform the industry", "leveraging".
The rewrite should state the concrete consequence in plain words (see "WHY IT MATTERS" \
examples above). It is better to say nothing than to hedge.

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
            "TIMEFRAME: do NOT mention any timeframe, cadence, or the word 'news' "
            "in the post. See the TIMEFRAME RULE in the system prompt.",
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
    lookback_hours: int = 168,  # kept for API stability; not surfaced in the post anymore
) -> tuple[str, list[str]]:
    """Call the LLM to draft a post. Returns (body, hashtags)."""
    if len(trends) < 3:
        raise ValueError(f"draft_post requires exactly 3 trends, got {len(trends)}")
    del lookback_hours  # intentionally unused; see TIMEFRAME RULE in SYSTEM_INSTRUCTIONS

    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        temperature=0.7,
        messages=[
            {"role": "system", "content": SYSTEM_INSTRUCTIONS},
            {
                "role": "user",
                "content": _user_message(trends[:3], voice, formatting),
            },
        ],
    )
    raw = response.choices[0].message.content or "{}"
    data = json.loads(raw)
    body = str(data.get("body", "")).strip()
    hashtags = [str(h).lstrip("#").strip() for h in data.get("hashtags", []) if str(h).strip()]
    if not body:
        raise RuntimeError("LLM returned empty post body")
    return body, hashtags
