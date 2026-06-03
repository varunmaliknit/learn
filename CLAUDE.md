# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install
pip install -e ".[dev]"

# Test
pytest                          # all tests
pytest tests/linkedin_agent/    # one package
pytest tests/ -k test_slugify   # one test by name

# Lint
ruff check src/ tests/
```

## Architecture

Two independent CLI agents share a single `pyproject.toml` package but have no code dependencies on each other.

### Stock Portfolio Agent (`stock_agent`)

Daily email digest of a YAML-configured stock portfolio.

**Flow:** `portfolio.yaml` → price/news/earnings/dividends monitors (`monitors/`) → OpenAI news summarizer (`ai/summarizer.py`) → Jinja2 HTML digest (`digest.py`) → SMTP email. APScheduler fires at 08:00 UK time; `--run-once` and `--dry-run` skip the scheduler.

Entry point: `stock-agent` CLI → `main.py`

### LinkedIn AI-Trends Agent (`linkedin_agent`)

Weekly automated LinkedIn post: finds trend signals, drafts a post, emails it for approval, then publishes.

**Flow (draft phase):**
1. `search.gather_candidate_pool()` — OpenAI web search + 21 RSS feeds, ~5-week evidence window
2. `ranker.rank_candidates()` — dedup, cross-source boost, recency decay → top-25 pool
3. `synthesizer.synthesize_themes()` — LLM clusters pool into evidence-backed `Theme` objects (index-referenced, no hallucination of events)
4. `main._select_publishable_themes()` — quality gates (`min_evidence_per_theme`, `min_theme_strength`)
5. `writer.draft_post(themes)` — LLM writes FROM cited evidence; `SYSTEM_INSTRUCTIONS_SINGLE` (default) or `MULTI`
6. `formatter.finalize()` — length enforcement, emoji/hashtag policy
7. `Draft(themes=…, trends=union)` → GitHub Issue + HTML preview email

**Approval flow:** Email link → Cloudflare Worker (`worker/src/index.ts`) verifies HMAC-SHA256 → dispatches `repository_dispatch` to GitHub → `linkedin-publish.yml` workflow runs `linkedin-agent publish` → LinkedIn REST API → closes issue.

Alternative: comment `/approve` or `/reject` on the draft issue.

Entry point: `linkedin-agent` CLI → `main.py`

### Key data model

```
Trend          # single article: title, url, source, summary, impact_score, published_at
Theme          # pattern: thesis, direction, supporting: list[Trend], strength_score, novelty_score
Draft          # post: body, hashtags, themes: list[Theme], trends: list[Trend] (deduped union)
```

`Draft.trends` is always populated as the deduped union of all `theme.supporting` items so legacy consumers (email, issue body, dry-run) work without knowing about themes.

### Post body integrity

The GitHub Issue body wraps the post in HTML comment markers:

```
<!-- linkedin-post START -->
…post text…
<!-- linkedin-post END -->
```

`github_issue.extract_post_from_body()` parses these. **Never change the marker strings** — the Cloudflare Worker and publish workflow depend on them.

## Configuration

Both agents are fully env-var driven. Copy `.env.example` to `.env`.

**LinkedIn agent tuning knobs** (all have defaults; override via env or GitHub Actions variables):

| Env var | Default | Effect |
|---|---|---|
| `LINKEDIN_AGENT_NUM_THEMES` | `1` | 1 = single deep-trend post; 3 = classic three-bullet |
| `LINKEDIN_AGENT_EVIDENCE_WINDOW_HOURS` | `840` | ~5-week candidate pool lookback |
| `LINKEDIN_AGENT_MIN_EVIDENCE_PER_THEME` | `3` | corroborating data points required per theme |
| `LINKEDIN_AGENT_MIN_THEME_STRENGTH` | `6.0` | theme strength floor (0–10); raise to skip weak weeks |
| `LINKEDIN_AGENT_SYNTHESIS_MODEL` | *(openai_model)* | point at a stronger reasoning model for synthesis |
| `LINKEDIN_AGENT_MAX_CANDIDATES` | `25` | pool size fed to synthesizer |

`voice.yaml` controls the writing persona and provides few-shot sample posts. Copy `voice.yaml.example` to `voice.yaml` and edit before first run.

## Infrastructure

- **GitHub Actions** — `linkedin-weekly-draft.yml` (Mon 14:00 UTC, gated on `LINKEDIN_AGENT_ENABLED=true`), `linkedin-publish.yml` (on dispatch / issue comment), `daily-digest.yml` (07:00 UTC daily)
- **Cloudflare Worker** — `worker/` directory; deploy with `npx wrangler deploy`; secrets set via `wrangler secret put APPROVAL_HMAC_SECRET` and `wrangler secret put GITHUB_TOKEN`
- `linkedin-agent secrets-template` prints a checklist of all required GitHub Actions secrets
