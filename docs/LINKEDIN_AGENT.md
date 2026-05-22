# LinkedIn AI-Trends Post Agent

A daily agent that:

1. Web-searches for the highest-impact AI news from the **last 24 hours**.
2. Drafts a LinkedIn post in your voice (3 trends, links, hashtags, formatting baked in).
3. Emails you a preview with a big **Approve & Post** button.
4. On approve — one click in the email — publishes to your LinkedIn profile and emails you the live link.

No new servers to host: GitHub Actions for the cron + a tiny Cloudflare Worker (free) for the one-click button.

---

## How approval works

```
GitHub Actions (cron, daily)
   │
   ▼
[draft] → opens a GitHub Issue with the draft as the body
       → emails you a preview with [Approve] [Edit on GitHub] [Reject] buttons
                          │
            click Approve in email (one click)
                          ▼
              Cloudflare Worker (verifies HMAC signature)
                          ▼
              GitHub repository_dispatch event
                          ▼
GitHub Actions [publish]
   ├── reads the current issue body  ← honors any edits you made on GitHub
   ├── POSTs to LinkedIn /rest/posts
   └── comments back on the issue with the live URL
```

You can also approve from inside the issue by commenting `/approve` (handy on mobile).

---

## One-time setup

### 1. Create a LinkedIn Developer App

1. Go to <https://www.linkedin.com/developers/apps> and click **Create app**.
2. Fill in name, your LinkedIn page (any company page you own — or create one), upload a logo.
3. In **Products**, add:
   - **Sign In with LinkedIn using OpenID Connect** (auto-approved)
   - **Share on LinkedIn** (auto-approved)
4. In **Auth** → **OAuth 2.0 settings**, add an Authorized Redirect URL:
   - `http://localhost:8000/callback`
5. Copy your **Client ID** and **Client Secret** from the Auth tab.

### 2. Run the OAuth helper

```bash
pip install -e .
linkedin-agent oauth
```

It will print step-by-step instructions, open LinkedIn's authorize page in your browser,
ask you to paste back the `code` from the redirect URL, and print the four secrets you
need to set in GitHub.

### 3. Deploy the Cloudflare Worker

See [`worker/README.md`](../worker/README.md). You'll need a free Cloudflare account.
Total time: about 3 minutes.

### 4. Add a voice file

```bash
cp voice.yaml.example voice.yaml
# Edit voice.yaml: paste in 2-3 of your past LinkedIn posts as voice anchors.
```

You can keep `voice.yaml` out of git (it's in `.gitignore`) or commit it — either way
the workflow falls back to `voice.yaml.example` if no `voice.yaml` is present.

### 5. Set GitHub Actions secrets and variables

In your repo → Settings → Secrets and variables → Actions:

**Secrets:**

| Name | How to get it |
|---|---|
| `OPENAI_API_KEY` | already set |
| `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_TO` | already set |
| `LINKEDIN_CLIENT_ID` | from `linkedin-agent oauth` |
| `LINKEDIN_CLIENT_SECRET` | from `linkedin-agent oauth` |
| `LINKEDIN_ACCESS_TOKEN` | from `linkedin-agent oauth` |
| `LINKEDIN_MEMBER_URN` | from `linkedin-agent oauth` |
| `APPROVAL_HMAC_SECRET` | `openssl rand -hex 32`; same value goes into the Worker |
| `APPROVER_WORKER_URL` | from `wrangler deploy` output, e.g. `https://linkedin-approver.<sub>.workers.dev` |

**Variables** (Variables tab, not Secrets):

| Name | Value |
|---|---|
| `LINKEDIN_AGENT_ENABLED` | `true` |
| `LINKEDIN_AGENT_MIN_IMPACT` | `6.0` (optional override; 0–10 scale) |

The daily workflow is **gated on `LINKEDIN_AGENT_ENABLED=true`** — it does nothing
until you set this variable. Use this to keep the workflow inert while you finish setup.

### 6. (Optional) Test it

```bash
# Dry run — prints the draft without emailing or opening an issue
linkedin-agent draft --dry-run

# Trigger the daily workflow manually
gh workflow run linkedin-daily-draft.yml
```

---

## Daily flow (after setup)

- 07:00 UTC: `linkedin-daily-draft.yml` runs.
- ~07:01 UTC: you get an email with the rendered preview.
- You click **Approve** → ~5 seconds later your post is live on LinkedIn.
- You get a confirmation email with the live URL.

If the day has no genuinely high-impact AI news (top trend impact < `LINKEDIN_AGENT_MIN_IMPACT`),
the agent skips posting and just emails you a short note instead of filler content.

---

## Formatting policy

Baked into the writer and enforced by `formatter.py`:

- **Bullets-as-emoji only** (🔹 markers). No other emoji anywhere.
- Hook (1–2 lines) → bridge → 3 bullets with URLs → bigger picture → CTA → hashtags.
- 1,200–1,800 chars (sweet spot for LinkedIn dwell time).
- 4–6 hashtags, evergreen tags (`#AI`, `#MachineLearning`) always present.
- No `[markdown](links)` — LinkedIn renders raw URLs only.
- Bans clichés (`game-changer`, `revolutionize`, `thoughts? 👇`, etc.) via the avoid-phrases list.

Tweak `src/linkedin_agent/config.py:FormattingConfig` or your `voice.yaml` to adjust.

---

## Token rotation

LinkedIn access tokens last about **60 days**. When yours expires, the daily run will
log a 401 and the post will fail. Just re-run `linkedin-agent oauth` and update
the `LINKEDIN_ACCESS_TOKEN` secret. This is the only recurring maintenance.

---

## CLI reference

```
linkedin-agent draft                 # daily flow: search + draft + issue + email
linkedin-agent draft --dry-run       # print to stdout, no side effects
linkedin-agent publish --issue 42    # publish from a specific issue
linkedin-agent reject --issue 42     # mark issue rejected, close
linkedin-agent oauth                 # one-time LinkedIn OAuth helper
linkedin-agent secrets-template      # dump JSON template of required env secrets
```

---

## Architecture

```
src/linkedin_agent/
├── main.py                    # CLI: draft / publish / reject / oauth
├── config.py                  # env-driven config
├── models.py                  # Trend, Draft
├── search.py                  # OpenAI web_search + RSS supplement
├── ranker.py                  # impact ranking + cross-source dedupe
├── writer.py                  # LLM drafter (system prompt + voice few-shots)
├── formatter.py               # length cap, hashtag/emoji policy, URL hygiene
├── email_preview.py           # Jinja HTML + plain text + SMTP send
├── github_issue.py            # issue create/parse/comment via GitHub REST API
├── linkedin_client.py         # /rest/posts publisher + token health check
├── oauth_helper.py            # interactive OAuth flow
└── signed_url.py              # HMAC-signed approve/reject links

worker/                        # Cloudflare Worker (one-click email button)
.github/workflows/
├── linkedin-daily-draft.yml   # cron + workflow_dispatch
└── linkedin-publish.yml       # repository_dispatch + issue_comment trigger
```
