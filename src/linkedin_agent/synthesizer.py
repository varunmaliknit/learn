"""Cluster a pool of candidate Trends into named Themes for post synthesis.

Each Theme is a real, evidence-backed pattern: a thesis, a directional claim,
and 2–4 corroborating Trend data points.  The writer then composes FROM the
evidence rather than needing to invent a connection from a single event.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from openai import OpenAI

from linkedin_agent.models import Theme, Trend, _slugify

logger = logging.getLogger(__name__)

# Weights for the theme selection score.  Evidence is saturating so a genuine
# multi-point pattern beats a single high-impact event.
_W_EVIDENCE: float = 0.8   # per data point (with saturation)
_W_NOVELTY: float = 0.4    # non-obviousness bonus
_EVIDENCE_SAT: int = 4     # evidence beyond this adds little

_SYNTHESIS_SYSTEM = """\
You are an AI trend analyst helping to identify genuine, evidence-backed patterns \
in the AI space for a LinkedIn post aimed at a mixed audience: experienced AI \
practitioners AND professionals in banking and enterprise tech (risk managers, \
data science leads, fintech PMs, CTOs, engineers in financial services).

Your job is to CLUSTER a pool of recent AI items into a small number of coherent \
THEMES — named patterns or trajectories, each backed by multiple concrete data points.

## Rules

EVIDENCE INTEGRITY (CRITICAL):
- Every theme's supporting items MUST be referenced by their integer index "i" from \
the input. Do NOT invent, summarise, or paraphrase events — only cite real items \
from the provided pool. A theme with fabricated supporting items will be discarded.
- If items in the pool do not form a genuine pattern together, produce FEWER themes \
(or none for that cluster) rather than forcing a connection that isn't there.

THEME QUALITY:
- A theme is a TRAJECTORY or PATTERN, not a single event. It answers: "What shift \
is underway, and where is it heading?"
- The thesis must be specific and directional: "Inference cost is collapsing faster \
than model capability is growing" is good. "AI is advancing rapidly" is not.
- Each theme must have at least {min_evidence} supporting items.

TOPIC FOCUS (CRITICAL — affects which themes to surface):
- PRIORITISE patterns in: AI engineering & tooling (agents, evals, inference/serving, \
dev tools), model capabilities (latency, context, architecture shifts, benchmarks), \
applied/enterprise adoption (real deployment patterns, ROI signals, org change), \
research breakthroughs (papers with concrete capability or safety results).
- ALSO PRIORITISE financial-services AI patterns: AI in fraud detection, credit risk, \
AML/KYC, copilots for analysts or advisors, core banking modernisation, model risk \
management (SR 11-7, Basel IV), RegTech (EU AI Act in banking, FCA/OCC guidance). \
A theme naming a specific bank or regulator as the actor is more valuable than a \
theme about AI labs alone — banking/fintech practitioners need to see their world.
- DE-PRIORITISE: pure funding/valuation themes with no technical substance, generic \
"Big Tech invests in AI" narratives, executive predictions without supporting facts, \
"banks partner with AI vendor" announcements with no deployment specifics.

NOVELTY:
- Prefer non-obvious patterns over things every practitioner already knows.
- "LLMs are getting cheaper" is low-novelty. "The capability-per-dollar curve is \
causing agent loop economics to flip from latency-bound to cost-bound" is high-novelty.
- For banking themes: "AI is coming to banking" is low-novelty. "SR 11-7 model risk \
review cycles are now the bottleneck that determines whether a bank's AI pilot makes \
it to production — and agentic audit tools are starting to cut that cycle from 6 months \
to 6 weeks" is high-novelty.

SCORING:
Calibrate strength_score on the same 0–10 scale used elsewhere:
  10 = paradigm-shifting, once-a-year pattern
   8 = strong, clear market/capability shift backed by named evidence
   6 = solid practitioner-relevant signal
   4 = incremental / incremental trend
   2 = weak or forced grouping
Calibrate novelty_score:
  10 = highly contrarian, surprising insight
   7 = non-obvious to most practitioners
   4 = known trend with good specifics
   1 = everyone already knows this

## Output format

Return STRICT JSON matching this schema, no prose:
{
  "themes": [
    {
      "thesis": "string — named pattern, one punchy sentence",
      "direction": "string — where this is heading for builders/teams, one sentence",
      "why_it_matters": "string — aggregate consequence for an AI practitioner, \
one tight sentence with a concrete implication (use the WHY_IT_MATTERS style: \
concrete actor + concrete consequence, never hedging like 'could reshape')",
      "supporting": [0, 3, 7],
      "strength_score": 7.5,
      "novelty_score": 6.0
    }
  ]
}

Return 3–6 themes, ordered by (strength_score + novelty_score) descending. \
Return FEWER if the evidence doesn't support more — empty themes are worse than no post."""


def _score_theme(theme: Theme) -> float:
    """Selection score: strength + saturating evidence bonus + novelty bonus."""
    ev = min(theme.evidence_count, _EVIDENCE_SAT)
    return theme.strength_score + _W_EVIDENCE * ev + _W_NOVELTY * theme.novelty_score


def _themes_from_json(
    data: dict[str, Any],
    candidates: list[Trend],
    min_evidence: int,
) -> list[Theme]:
    """Parse the LLM's theme JSON into Theme objects; drop invalid/weak themes."""
    themes: list[Theme] = []
    for raw in data.get("themes", []):
        try:
            thesis = str(raw.get("thesis", "")).strip()
            if not thesis:
                continue

            supporting_indices: list[int] = []
            for idx in raw.get("supporting", []):
                try:
                    i = int(idx)
                except (TypeError, ValueError):
                    continue
                if 0 <= i < len(candidates):
                    supporting_indices.append(i)
                else:
                    logger.debug(
                        "theme %r: dropping out-of-range index %d (pool size=%d)",
                        thesis, idx, len(candidates),
                    )

            # Dedupe indices while preserving order.
            seen: set[int] = set()
            unique_indices = [i for i in supporting_indices if not (i in seen or seen.add(i))]  # type: ignore[func-returns-value]
            supporting = [candidates[i] for i in unique_indices]

            if len(supporting) < min_evidence:
                logger.info(
                    "dropping theme %r: only %d supporting items (min=%d)",
                    thesis, len(supporting), min_evidence,
                )
                continue

            strength = float(raw.get("strength_score", 0.0))
            novelty = float(raw.get("novelty_score", 0.0))
            strength = max(0.0, min(10.0, strength))
            novelty = max(0.0, min(10.0, novelty))

            theme = Theme(
                thesis=thesis,
                direction=str(raw.get("direction", "")).strip(),
                why_it_matters=str(raw.get("why_it_matters", "")).strip(),
                supporting=supporting,
                strength_score=strength,
                novelty_score=novelty,
                theme_id=_slugify(thesis),
            )
            themes.append(theme)
        except Exception as e:  # noqa: BLE001
            logger.warning("skipping malformed theme item: %r — %s", raw, e)
            continue
    return themes


def synthesize_themes(
    api_key: str,
    model: str,
    candidates: list[Trend],
    num_themes: int = 1,
    min_evidence_per_theme: int = 3,
    temperature: float = 0.2,
) -> list[Theme]:
    """Cluster candidate Trends into named Themes backed by real evidence.

    Returns themes sorted by selection score, filtered to those meeting
    min_evidence_per_theme, trimmed to num_themes.

    Offline-testable: returns [] if api_key is empty or the candidate pool
    is too small, without calling OpenAI.
    """
    if not api_key:
        logger.warning("synthesize_themes: api_key is empty; returning no themes")
        return []
    if len(candidates) < min_evidence_per_theme:
        logger.warning(
            "synthesize_themes: only %d candidates (need >= %d); returning no themes",
            len(candidates), min_evidence_per_theme,
        )
        return []

    payload = [
        {
            "i": idx,
            "title": t.title,
            "source": t.source,
            "summary": (t.one_line_summary or "")[:280],
            "why_it_matters": (t.why_it_matters or "")[:240],
            "impact_score": round(t.impact_score, 1),
            "published_at": t.published_at.strftime("%Y-%m-%d") if t.published_at else "",
        }
        for idx, t in enumerate(candidates)
    ]

    system_prompt = _SYNTHESIS_SYSTEM.replace("{min_evidence}", str(min_evidence_per_theme))

    client = OpenAI(api_key=api_key)
    try:
        response = client.chat.completions.create(
            model=model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(payload)},
            ],
            temperature=temperature,
        )
        raw = response.choices[0].message.content or "{}"
    except Exception as e:  # noqa: BLE001
        logger.error("synthesize_themes: LLM call failed: %s", e)
        return []

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("synthesize_themes: LLM returned invalid JSON; returning no themes")
        return []

    themes = _themes_from_json(data, candidates, min_evidence_per_theme)
    if not themes:
        logger.warning("synthesize_themes: no valid themes after parsing; returning []")
        return []

    themes.sort(key=_score_theme, reverse=True)
    selected = themes[:num_themes]
    logger.info(
        "synthesize_themes: %d themes from pool of %d (returning %d):",
        len(themes), len(candidates), len(selected),
    )
    for i, th in enumerate(selected, 1):
        logger.info(
            "  %d. strength=%.1f novelty=%.1f evidence=%d  %r",
            i, th.strength_score, th.novelty_score, th.evidence_count, th.thesis[:80],
        )
    return selected
