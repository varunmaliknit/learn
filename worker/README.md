# LinkedIn Approver Worker

A tiny Cloudflare Worker that lets you approve or reject the daily LinkedIn
draft with **one click from your email** — no GitHub login required at the
moment of approval.

## How it works

1. The daily `linkedin-agent draft` GitHub Action signs two URLs with an HMAC:
   - `https://<worker>/a?d=<draft_id>&s=<sig>` — approve
   - `https://<worker>/r?d=<draft_id>&s=<sig>` — reject
2. Your approval email includes both as big buttons.
3. When you click, this Worker:
   - Verifies the signature against the shared secret
   - Calls GitHub's `POST /repos/<owner>/<repo>/dispatches` with
     `event_type: linkedin_approve` (or `linkedin_reject`)
4. The `linkedin-publish.yml` workflow handles the dispatch, reads the latest
   issue body, and posts to LinkedIn (or closes the issue on reject).

Total round trip: ~5 seconds from click to live post.

## One-time setup

Prereqs: a free Cloudflare account.

```bash
cd worker
npm install
npx wrangler login            # opens browser, ~30 seconds

# Edit GITHUB_OWNER / GITHUB_REPO in wrangler.toml if you forked the repo

# Generate a strong HMAC secret (32+ bytes):
openssl rand -hex 32

# Set the worker's secrets:
npx wrangler secret put APPROVAL_HMAC_SECRET   # paste the value from above
npx wrangler secret put GITHUB_TOKEN           # fine-grained PAT, see below

npx wrangler deploy
# Note the URL it prints — e.g. https://linkedin-approver.<sub>.workers.dev
```

### GitHub PAT scopes

Create a **fine-grained personal access token** at
<https://github.com/settings/personal-access-tokens/new>:

- Resource owner: your user
- Repository access: **Only select repositories** → `learn`
- Repository permissions:
  - **Contents: Read and write**

The "Contents: write" permission is what `POST /dispatches` requires. Nothing
else is needed.

## Wire it up to the agent

In your `learn` repo, set these **GitHub Actions secrets** (Settings → Secrets
and variables → Actions):

| Secret | Value |
|---|---|
| `APPROVAL_HMAC_SECRET` | Same value you gave the Worker |
| `APPROVER_WORKER_URL` | The `https://...workers.dev` URL from `wrangler deploy` |

Now the daily `linkedin-daily-draft.yml` action will email you signed URLs
that point at this Worker.

## Local development

```bash
npm run dev   # http://localhost:8787
# Test approve:
curl "http://localhost:8787/a?d=2026-05-22&s=$(printf 'approve|2026-05-22' | openssl dgst -sha256 -hmac '<your-hmac-secret>' -hex | cut -d' ' -f2)"
```

## Rotating the HMAC secret

If you ever leak the secret in an old email, rotate it:

```bash
openssl rand -hex 32                      # new value
npx wrangler secret put APPROVAL_HMAC_SECRET
gh secret set APPROVAL_HMAC_SECRET --body "<same value>" --repo varunmaliknit/learn
```

Old emails' Approve buttons will stop working — exactly the behavior you want.
