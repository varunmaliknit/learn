# Slack Jira Thread Tracker

MVP service that listens for Slack `app_mention` events in Socket Mode and creates or updates Jira Cloud issues from Slack thread context.

## Architecture

- `src/slack` owns Slack Bolt setup, command parsing, thread fetching, and transcript formatting.
- `src/services` coordinates idempotency, thread-to-Jira mappings, and create/update orchestration.
- `src/jira` isolates Jira Cloud REST API calls.
- `src/llm` isolates OpenAI extraction and validates the returned JSON shape.
- `src/db` owns the Prisma client and PostgreSQL persistence.
- `src/routes` exposes the Express health endpoint at `GET /health`.

The main flow is:

1. Slack sends an `app_mention` event over Socket Mode.
2. The event ID is claimed in `ProcessedEvent`; duplicates are skipped.
3. The command parser looks for `create ticket` or `track this`.
4. The service determines `thread_ts`, fetches replies, and builds a plain transcript.
5. OpenAI extracts Jira issue fields from the transcript.
6. If a `ThreadLink` exists, Jira receives a new comment and Slack gets an update reply.
7. If no `ThreadLink` exists, Jira receives a new issue, the mapping is stored, and Slack gets the issue link.

## Prerequisites

- Node.js 20.x
- npm
- Docker, for local PostgreSQL
- A Slack app with Socket Mode enabled
- A Jira Cloud API token
- An OpenAI API key

## Slack App Setup

Create a Slack app with:

- Socket Mode enabled
- An app-level token with `connections:write`
- A bot token with these OAuth scopes:
  - `app_mentions:read`
  - `channels:history`
  - `groups:history`
  - `chat:write`

Subscribe to the `app_mention` bot event. Install the app into the workspace and invite it to channels where it should listen.

## Local Setup

Install dependencies:

```bash
nvm use
npm install
```

If `nvm` is not installed, make sure `node -v` reports a 20.x runtime before running Prisma commands. Newer majors can fail with opaque Prisma schema-engine errors.

The npm scripts in this repo enforce Node 20.x and will exit early with a clear error if a different major is active.

Copy and fill environment variables:

```bash
cp .env.example .env
```

Start local PostgreSQL:

```bash
docker compose up -d postgres
```

Generate Prisma client and apply the initial migration:

```bash
npm run prisma:generate
npm run prisma:migrate
```

Run tests:

```bash
npm test
```

Start the service:

```bash
npm run dev
```

Health check:

```bash
curl http://localhost:3000/health
```

## Environment Variables

| Variable | Description |
| --- | --- |
| `SLACK_BOT_TOKEN` | Slack bot token, usually `xoxb-...` |
| `SLACK_APP_TOKEN` | Slack app-level Socket Mode token, usually `xapp-...` |
| `SLACK_SIGNING_SECRET` | Slack app signing secret |
| `JIRA_BASE_URL` | Jira Cloud base URL, for example `https://example.atlassian.net` |
| `JIRA_USER_EMAIL` | Jira account email for basic auth |
| `JIRA_API_TOKEN` | Jira Cloud API token |
| `JIRA_PROJECT_KEY` | Default Jira project key |
| `OPENAI_API_KEY` | OpenAI API key |
| `OPENAI_MODEL` | OpenAI model for extraction, defaults to `gpt-4o-mini` |
| `DATABASE_URL` | PostgreSQL connection string |
| `PORT` | Health server port |

## Usage

Mention the bot in a Slack thread:

```text
@bot create ticket
```

or:

```text
@bot track this
```

If the mention is not already inside a thread, the message timestamp becomes the thread timestamp and the service uses that message as the root.

Slack replies:

```text
Created Jira issue PROJ-123: <url|summary>
```

If the same Slack workspace, channel, and thread timestamp is already linked:

```text
Updated linked Jira issue PROJ-123
```

## Jira Notes

Jira Cloud API v3 usually expects rich text fields as Atlassian Document Format. The service accepts plain text internally and wraps it in a minimal ADF document inside `JiraClient`.

The configured Jira project must support the extracted issue type names: `Task`, `Bug`, and `Story`. If the project uses different issue type names, update the prompt and allowed values in `src/llm/extractor.ts`.

## Docker

Build the service image:

```bash
docker build -t slack-jira-thread-tracker .
```

The provided `docker-compose.yml` only runs local PostgreSQL. Run the Node service locally with `npm run dev`, or extend the compose file with an app service once deployment settings are known.

## Next Improvements

- Add a processing status to `ProcessedEvent` so failed events can be retried safely.
- Resolve Slack user IDs to display names in transcripts.
- Add Jira issue type and priority mapping per project.
- Add stronger OpenAI structured outputs with JSON schema response format.
- Add integration tests with mocked Slack, Jira, and OpenAI clients.
- Add metrics, request tracing, and alerting for failed ticket creation.
