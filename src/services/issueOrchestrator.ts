import type { WebClient } from '@slack/web-api';
import type { JiraClient } from '../jira/jiraClient.js';
import type { IssueExtraction, LlmExtractor } from '../llm/extractor.js';
import {
  buildThreadTranscript,
  type SlackThreadMessage,
  SlackThreadService
} from '../slack/threadService.js';
import type { ThreadLinkService } from './threadLinkService.js';
import type { Logger } from 'pino';

export interface HandleMentionInput {
  workspaceId: string;
  channelId: string;
  messageTs: string;
  threadTs?: string;
  jiraIssueKey?: string | null;
}

export type IssueOrchestratorResult =
  | {
      action: 'created';
      jiraIssueKey: string;
      jiraIssueUrl: string;
      summary: string;
      threadTs: string;
    }
  | {
      action: 'updated';
      jiraIssueKey: string;
      jiraIssueUrl: string;
      threadTs: string;
    };

export class IssueOrchestrator {
  private readonly slackThreadService: SlackThreadService;

  public constructor(
    slackClient: WebClient,
    private readonly threadLinkService: ThreadLinkService,
    private readonly jiraClient: JiraClient,
    private readonly llmExtractor: LlmExtractor,
    private readonly log: Logger
  ) {
    this.slackThreadService = new SlackThreadService(slackClient);
  }

  public async handleMention(input: HandleMentionInput): Promise<IssueOrchestratorResult> {
    const threadTs = this.slackThreadService.getThreadTs({
      ts: input.messageTs,
      thread_ts: input.threadTs
    });

    const linkRef = {
      workspaceId: input.workspaceId,
      channelId: input.channelId,
      threadTs
    };

    const messages = await this.slackThreadService.fetchThreadMessages({
      channelId: input.channelId,
      threadTs
    });
    const transcript = buildThreadTranscript(messages);
    const extraction = forceCreate(await this.llmExtractor.extractIssue(transcript));
    const existingLink =
      (await this.threadLinkService.findLink(linkRef)) ??
      (await this.recoverLinkFromThread(linkRef, messages, input.jiraIssueKey));

    if (existingLink) {
      await this.jiraClient.addComment(
        existingLink.jiraIssueKey,
        formatUpdateComment(extraction, transcript)
      );
      this.log.info(
        { jiraIssueKey: existingLink.jiraIssueKey, threadTs },
        'Updated existing Jira issue from Slack thread'
      );
      return {
        action: 'updated',
        jiraIssueKey: existingLink.jiraIssueKey,
        jiraIssueUrl: this.jiraClient.issueUrl(existingLink.jiraIssueKey),
        threadTs
      };
    }

    const issue = await this.jiraClient.createIssue({
      summary: extraction.summary,
      description: extraction.description,
      issueType: extraction.issueType,
      priority: extraction.priority
    });

    await this.threadLinkService.createLink({
      ...linkRef,
      jiraIssueKey: issue.key,
      jiraIssueId: issue.id
    });

    this.log.info({ jiraIssueKey: issue.key, threadTs }, 'Created Jira issue from Slack thread');

    return {
      action: 'created',
      jiraIssueKey: issue.key,
      jiraIssueUrl: issue.url,
      summary: extraction.summary,
      threadTs
    };
  }

  private async recoverLinkFromThread(
    linkRef: { workspaceId: string; channelId: string; threadTs: string },
    messages: SlackThreadMessage[],
    explicitJiraIssueKey?: string | null
  ) {
    const jiraIssueKey = explicitJiraIssueKey ?? findExistingJiraKey(messages);
    if (!jiraIssueKey) {
      return null;
    }

    const issue = await this.jiraClient.getIssue(jiraIssueKey);
    const recoveredLink = await this.threadLinkService.createLink({
      ...linkRef,
      jiraIssueKey: issue.key,
      jiraIssueId: issue.id
    });

    this.log.info({ jiraIssueKey: issue.key, threadTs: linkRef.threadTs }, 'Recovered missing thread link from Slack thread');

    return recoveredLink;
  }
}

export function formatUpdateComment(extraction: IssueExtraction, transcript: string): string {
  return [
    'Slack thread update summary:',
    '',
    extraction.description,
    '',
    'Latest transcript:',
    transcript
  ].join('\n');
}

function forceCreate(extraction: IssueExtraction): IssueExtraction {
  return {
    ...extraction,
    decision: 'create'
  };
}

function findExistingJiraKey(messages: SlackThreadMessage[]): string | null {
  for (const message of messages) {
    const match = message.text?.match(/\bCreated Jira issue ([A-Z][A-Z0-9_]*-\d+)\b/i);
    if (match?.[1]) {
      return match[1].toUpperCase();
    }
  }

  return null;
}
