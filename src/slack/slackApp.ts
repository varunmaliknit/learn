import bolt from '@slack/bolt';
import type { SlackEventMiddlewareArgs } from '@slack/bolt';
import type { Config } from '../config.js';
import type { JiraClient } from '../jira/jiraClient.js';
import type { LlmExtractor } from '../llm/extractor.js';
import { logger } from '../logger.js';
import { parseCommand } from './commandParser.js';
import type { IdempotencyService } from '../services/idempotencyService.js';
import { IssueOrchestrator } from '../services/issueOrchestrator.js';
import type { ThreadLinkService } from '../services/threadLinkService.js';

const { App } = bolt;

interface SlackEventBody {
  event_id?: string;
  team_id?: string;
}

export interface SlackAppDependencies {
  config: Config;
  threadLinkService: ThreadLinkService;
  idempotencyService: IdempotencyService;
  jiraClient: JiraClient;
  llmExtractor: LlmExtractor;
}

export function createSlackApp(deps: SlackAppDependencies) {
  const app = new App({
    token: deps.config.SLACK_BOT_TOKEN,
    appToken: deps.config.SLACK_APP_TOKEN,
    signingSecret: deps.config.SLACK_SIGNING_SECRET,
    socketMode: true
  });

  const orchestrator = new IssueOrchestrator(
    app.client,
    deps.threadLinkService,
    deps.jiraClient,
    deps.llmExtractor,
    logger
  );

  app.event('app_mention', async (args: SlackEventMiddlewareArgs<'app_mention'>) => {
    const { event } = args;
    const body = args.body as SlackEventBody;
    const eventId = body.event_id;
    const workspaceId = body.team_id ?? event.team;

    if (!eventId) {
      logger.warn({ event }, 'Slack app_mention missing event_id');
      return;
    }

    if (!workspaceId) {
      logger.warn({ eventId, event }, 'Slack app_mention missing workspace ID');
      return;
    }

    const claimed = await deps.idempotencyService.claimEvent(eventId, 'app_mention');
    if (!claimed) {
      logger.info({ eventId }, 'Skipping duplicate Slack event');
      return;
    }

    const parsed = parseCommand(event.text ?? '');
    if (parsed.intent === 'ignore') {
      logger.info({ eventId, normalizedText: parsed.normalizedText }, 'Ignoring app mention');
      return;
    }

    const threadTs = event.thread_ts ?? event.ts;

    try {
      const result = await orchestrator.handleMention({
        workspaceId,
        channelId: event.channel,
        messageTs: event.ts,
        threadTs: event.thread_ts,
        jiraIssueKey: parsed.jiraIssueKey
      });

      const text =
        result.action === 'created'
          ? `Created Jira issue ${result.jiraIssueKey}: <${result.jiraIssueUrl}|${result.summary}>`
          : `Updated linked Jira issue ${result.jiraIssueKey}`;

      await app.client.chat.postMessage({
        channel: event.channel,
        thread_ts: result.threadTs,
        text
      });
    } catch (error) {
      logger.error({ err: error, eventId, threadTs }, 'Failed to process Slack thread');
      await app.client.chat.postMessage({
        channel: event.channel,
        thread_ts: threadTs,
        text: 'Sorry, I could not create or update the Jira issue for this thread.'
      });
    }
  });

  return app;
}
