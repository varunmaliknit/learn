"""LLM-based LinkedIn post writer.

Drafts a post from synthesized Themes (each backed by 3-4 real data points)
rather than from single news items.  The writer composes FROM evidence; the
synthesis layer already owns pattern-finding.

Default structure (num_themes=1): one deep trend per post — a single thesis
developed across 3-4 🔹 evidence bullets, matching the user's voice sample #2.

Multi-theme structure (num_themes>=2): one 🔹 bullet per theme, each with
its own thesis and 2-3 cited data points per bullet.
"""

from __future__ import annotations

import json
import logging

from openai import OpenAI

from linkedin_agent.config import FormattingConfig, VoiceConfig
from linkedin_agent.models import Theme

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


def _themes_block(themes: list[Theme]) -> str:
    """Render themes with their concrete supporting evidence for the writer."""
    out = ["THEMES TO COVER (the patterns are real — compose from the evidence below):"]
    for i, theme in enumerate(themes, 1):
        out.append(f"\n--- THEME {i} ---")
        out.append(f"Thesis: {theme.thesis}")
        out.append(f"Direction: {theme.direction}")
        out.append(f"Why it matters: {theme.why_it_matters}")
        out.append(f"Supporting evidence ({len(theme.supporting)} data points):")
        for j, t in enumerate(theme.supporting, 1):
            out.append(f"  {j}. {t.title}")
            out.append(f"     What happened: {t.one_line_summary}")
            out.append(f"     Why it matters: {t.why_it_matters}")
    return "\n".join(out)


SYSTEM_INSTRUCTIONS_SINGLE = """\
You are a LinkedIn ghostwriter for an experienced AI practitioner.
Output ONE LinkedIn post that follows these rules EXACTLY.

POST STRUCTURE (single deep trend, this exact order):
1. A 1-line HOOK: the thesis as a bold directional statement or counterintuitive \
angle. No emoji. Keep it tight — this is the thesis sentence readers share.
2. Exactly N bullets (🔹 marker), one per supporting data point:
   - Each bullet names ONE concrete data point from the evidence provided \
(see SPECIFICITY RULE) and explains in 1 tight sentence why that data point \
is evidence of the thesis.
   - Do NOT add URLs. Do NOT add a source line.
3. A 1-2 sentence "where this is heading" paragraph — what the pattern implies \
for builders/teams in the next 6-12 months. Plain prose, no bullet.
4. A CTA — ONE specific question grounded in the thesis (see CTA RULES).

The post reads as: "here is a real pattern, here is the proof, here is where it's going."

EVIDENCE RULE (CRITICAL — replaces the old "pretend it's a trend" coaching):
The pattern is real and given to you — you do NOT need to invent a connection.
Your job is to state the thesis crisply and back it with the NAMED events provided.
Do NOT invent facts, statistics, or companies beyond what the evidence supplies.
If a supporting item lacks a concrete detail, use the "What happened" text as-is; \
never substitute vague marketing-speak for a missing specific.

TIMEFRAME RULE (CRITICAL):
- Do NOT mention time windows, cadences, or the word "news". No "this week", \
"today", "recently", "in the last few days", "just dropped", "breaking".
- The post reads as evergreen trend analysis, not a weekly news roundup.

SPECIFICITY RULE (CRITICAL):
- Every bullet MUST name the specific entity: product name, model name, paper title, \
dollar amount, benchmark result, named regulation, org-vs-org move, concrete metric.
- BAD: "X announced advancements in its AI-driven capabilities."
- GOOD: "OpenAI shipped GPT-5o-mini at $0.15 per million input tokens — 5x cheaper \
than 4o-mini."
- If you were given a specific name or number, USE IT.

FORMATTING RULES (STRICT):
- The bullet marker (🔹 by default) is the ONLY emoji allowed. No other emoji anywhere.
- Do NOT include URLs in the post body. Sources live outside the post.
- Do NOT include hashtags.
- Use plain prose. No bold, no italics, no markdown headings.
- Body length: the exact target range is given in the user message as MIN= and MAX= values.

VOICE RULES (CRITICAL):
- Write in CONCRETE language, not analyst-speak. Match the user's voice samples closely.
- BANNED stock phrases (do NOT use any): "game changer", "revolutionize", \
"reshape the landscape", "reshaping ... dynamics", "transform the industry", \
"unlock new possibilities", "unlock value", "shifting paradigms", "paving the way", \
"in today's fast-paced world", "democratize AI" / "democratize anything", \
"leveraging" / "leverage" (use "use"), "empower" / "empowering", \
"accelerate" when meaning faster (use "speed up"), "strategic", "synergy", \
"ecosystem" (use "market" / "stack" / be specific), "poised to", \
"in the AI landscape" / "AI landscape", "stirring up competition", "thoughts? 👇", \
"I'm thrilled", "I'm excited", "without breaking the bank", "on the horizon", \
"a fascinating time", "push boundaries", "next frontier", "uncharted territory", \
"jaw-dropping", "staggering" (use the number), "connect the dots", "raising the bar", \
"playing field", "weaving itself", "deeper into our lives", "buzzing", "seamlessly", \
"merging digital and physical worlds", "redefining how we interact".
- BANNED bureaucratic verbs: utilize, facilitate, enable (the abstract sense), \
incentivize, operationalize, optimize (unless literal), enhance (use "improve"), \
drive (as in "drives growth").
- BANNED hedging adverbs: "potentially", "significantly" (unless followed by a number), \
"likely", "increasingly", "substantially". Cut them or replace with a number / example.
- For the "where this is heading" paragraph: state ONE concrete implication \
(a specific use-case, a specific number, a specific technical decision, a specific \
buyer/builder consequence). Never say something "could reshape" — say what changes for whom.

"WHY IT MATTERS" (for bullets and the direction paragraph) — STUDY THESE PATTERNS:
BAD: "this reshapes AI hardware dynamics."
GOOD (single consequence): "teams buying H100s now have a second supplier to play \
against on price."
BETTER (trend implication): "the hyperscaler-as-buyer monopsony for frontier \
accelerators is cracking — for the first time AI infra teams have credible leverage \
on price-per-FLOP at the procurement table."
Pattern: concrete actor + concrete consequence + (when possible) a specific number, \
competitor, decision, or use-case. One tight sentence.

CTA RULES:
- The CTA must be a SPECIFIC question grounded in the thesis and the evidence.
- BAD: "What do you think these shifts mean?" — too generic.
- GOOD shape: "For [specific role / builder type]: does [the pattern] change \
[specific decision / stack choice / process], and what would you do differently?"
- ONE question, max two sentences.

SELF-CHECK before returning JSON:
If the body contains ANY of these, rewrite that sentence:
"potentially", "could solidify", "could revolutionize", "might catalyze", \
"may reshape", "may alter", "likely to", "increasingly", "substantially", \
"significantly" (unless followed by a number), "highlights", "underscores", \
"stirring up", "game changer", "game-changer", "reshape", "reshaping", \
"transform the industry", "leveraging".
The rewrite states the concrete consequence in plain words.

OUTPUT FORMAT (STRICT JSON, no surrounding prose):
{
  "body": "the full post text following the structure above"
}

Do NOT include a "hashtags" key. Do NOT include any URLs in the body."""


SYSTEM_INSTRUCTIONS_MULTI = """\
You are a LinkedIn ghostwriter for an experienced AI practitioner.
Output ONE LinkedIn post that follows these rules EXACTLY.

POST STRUCTURE (multi-theme, this exact order):
1. A 1-line HOOK that signals stakes or a counterintuitive angle across the themes. \
No emoji. Keep it short.
2. Exactly N bullets (🔹 marker), one per theme, in the order given:
   - Bullet marker + the theme thesis as a concrete directional statement.
   - Then 1-2 tight sentences citing 2-3 specific data points from that theme's evidence.
   - "Why it matters:" one tight clause — the concrete practitioner implication.
   - Do NOT add URLs or source lines.
3. A CTA — ONE specific question grounded in the themes (see CTA RULES).

EVIDENCE RULE (CRITICAL):
The patterns are real and given to you — do NOT invent connections.
State each thesis and back it with the NAMED events provided.
Do NOT fabricate facts, statistics, or companies beyond the supplied evidence.

TIMEFRAME RULE (CRITICAL):
No "this week", "today", "recently", "just dropped", "breaking", "news".
The post reads as evergreen trend analysis.

SPECIFICITY RULE (CRITICAL):
Every bullet MUST name specific entities: product names, dollar amounts, \
benchmark results, named regulations, concrete metrics. No generic descriptions.
BAD: "X announced advancements." GOOD: "OpenAI shipped GPT-5o-mini at $0.15/M tokens."

FORMATTING RULES (STRICT):
- 🔹 is the ONLY emoji allowed.
- No URLs, no hashtags, plain prose, no markdown.
- Body length: the exact target range is given in the user message as MIN= and MAX= values.

VOICE RULES (CRITICAL):
- Concrete language, not analyst-speak. Match voice samples closely.
- BANNED: "game changer", "revolutionize", "reshape the landscape", "transform the industry", \
"unlock new possibilities", "leveraging", "empower", "accelerate" (use "speed up"), \
"strategic", "synergy", "ecosystem" (use "market"/"stack"), "poised to", \
"AI landscape", "I'm thrilled", "I'm excited", "thoughts? 👇", "on the horizon", \
"push boundaries", "next frontier", "seamlessly", "jaw-dropping", "staggering" (use the number).
- BANNED verbs: utilize, facilitate, operationalize, enhance (use "improve").
- BANNED hedges: "potentially", "likely", "increasingly", "substantially", \
"significantly" (unless followed by a number).
- "Why it matters:" = concrete actor + concrete consequence. Never hedge.

CTA RULES:
ONE specific question grounded in the themes. Not "what do you think?".
Shape: "For [specific builder type]: does [pattern] force you to [specific decision]?"

SELF-CHECK:
Rewrite any sentence containing: "potentially", "could solidify", "might catalyze", \
"may reshape", "likely to", "increasingly", "significantly" (without a number), \
"highlights", "underscores", "game changer", "reshape", "leveraging".

OUTPUT FORMAT (STRICT JSON, no surrounding prose):
{
  "body": "the full post text following the structure above"
}

Do NOT include "hashtags" or any URLs in the body."""


def _user_message(
    themes: list[Theme],
    voice: VoiceConfig,
    formatting: FormattingConfig,
    num_themes: int,
) -> str:
    n_bullets = num_themes if num_themes > 1 else len(themes[0].supporting)
    parts = [
        _voice_block(voice),
        f"BULLET MARKER: {formatting.bullet_marker}",
        f"NUMBER OF BULLETS (N): {n_bullets}",
        "TIMEFRAME: do NOT mention any timeframe, cadence, or the word 'news'. "
        "See the TIMEFRAME RULE in the system prompt.",
        f"LENGTH (total post): MIN={formatting.min_chars}, "
        f"MAX={formatting.max_chars} characters. Aim near the middle of that range.",
        "URLS: do NOT include any URLs in the body. Sources live outside the post.",
        "HASHTAGS: do NOT include any hashtags.",
        _themes_block(themes),
        "Now write the post and return the JSON.",
    ]
    return "\n\n".join(parts)


def draft_post(
    api_key: str,
    model: str,
    themes: list[Theme],
    voice: VoiceConfig,
    formatting: FormattingConfig,
    num_themes: int = 1,
    lookback_hours: int = 168,  # kept for API stability; not surfaced in post
) -> tuple[str, list[str]]:
    """Draft a LinkedIn post from synthesized Themes.

    num_themes=1 (default): single deep trend, one thesis with 3-4 evidence bullets.
    num_themes>=2: one bullet per theme in the classic multi-topic format.

    Returns (body, hashtags).
    """
    del lookback_hours  # intentionally unused; see TIMEFRAME RULE

    if len(themes) < num_themes:
        raise ValueError(
            f"draft_post requires {num_themes} theme(s), got {len(themes)}"
        )

    system_prompt = SYSTEM_INSTRUCTIONS_SINGLE if num_themes == 1 else SYSTEM_INSTRUCTIONS_MULTI

    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        temperature=0.7,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": _user_message(themes[:num_themes], voice, formatting, num_themes),
            },
        ],
    )
    raw = response.choices[0].message.content or "{}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("draft_post: LLM returned invalid JSON: %s", exc)
        raise RuntimeError("LLM returned invalid JSON for post body") from exc
    body = str(data.get("body", "")).strip()
    hashtags = [str(h).lstrip("#").strip() for h in data.get("hashtags", []) if str(h).strip()]
    if not body:
        raise RuntimeError("LLM returned empty post body")
    return body, hashtags
