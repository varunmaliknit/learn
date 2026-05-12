import type { WebClient } from '@slack/web-api';
import type { JiraClient, JiraIssueDetails } from '../jira/jiraClient.js';
import type { IssueExtraction, IssueSyncPlan, LlmExtractor } from '../llm/extractor.js';
import {
  buildThreadTranscript,
  type SlackThreadMessage,
  SlackThreadService
} from '../slack/threadService.js';
import type { ThreadLinkService } from './threadLinkService.js';
import type { Logger } from 'pino';
import {
  formatJiraDescription,
  normalizeDescriptionSections,
  parseJiraDescription
} from './jiraDescriptionFormatter.js';

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
      updateSummary: string;
      threadTs: string;
    }
  | {
      action: 'no_change';
      jiraIssueKey: string;
      jiraIssueUrl: string;
      updateSummary: string;
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
      const currentIssue = await this.jiraClient.getIssue(existingLink.jiraIssueKey);
      const syncPlan = await this.llmExtractor.planIssueSync({
        transcript,
        jiraSummary: currentIssue.summary,
        jiraDescription: currentIssue.description,
        jiraRecentComments: currentIssue.recentComments
      });

      return this.applySyncPlan(currentIssue, syncPlan, transcript, threadTs);
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

  private async applySyncPlan(
    issue: JiraIssueDetails,
    syncPlan: IssueSyncPlan,
    transcript: string,
    threadTs: string
  ): Promise<IssueOrchestratorResult> {
    const currentSections = parseJiraDescription(issue.summary, issue.description);
    const nextSections = normalizeDescriptionSections(syncPlan.descriptionSections, currentSections);
    const nextDescription = formatJiraDescription(nextSections);
    const nextSummary = syncPlan.summary ?? issue.summary;

    const summaryChanged = !equivalentText(issue.summary, nextSummary);
    const descriptionChanged = !equivalentText(issue.description, nextDescription);
    const comment = syncPlan.comment;
    const shouldAddComment = Boolean(comment);

    if (!summaryChanged && !descriptionChanged && !shouldAddComment) {
      this.log.info(
        { jiraIssueKey: issue.key, threadTs, reasoning: syncPlan.reasoning, modelDecision: syncPlan.decision },
        'No Jira update required from Slack thread'
      );

      return {
        action: 'no_change',
        jiraIssueKey: issue.key,
        jiraIssueUrl: issue.url,
        updateSummary: 'no changes needed',
        threadTs
      };
    }

    let updateSummary = describeAppliedChanges(summaryChanged, descriptionChanged, shouldAddComment);

    if (summaryChanged || descriptionChanged) {
      await this.jiraClient.updateIssue(issue.key, {
        summary: summaryChanged ? nextSummary : undefined,
        description: descriptionChanged ? nextDescription : undefined
      });
    }

    if (comment) {
      await this.jiraClient.addComment(issue.key, comment);
    }

    this.log.info(
      {
        jiraIssueKey: issue.key,
        threadTs,
        modelDecision: syncPlan.decision,
        reasoning: syncPlan.reasoning,
        summaryChanged,
        descriptionChanged,
        commentAdded: shouldAddComment
      },
      'Updated existing Jira issue from Slack thread'
    );

    return {
      action: 'updated',
      jiraIssueKey: issue.key,
      jiraIssueUrl: issue.url,
      updateSummary,
      threadTs
    };
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

function equivalentText(left: string, right: string): boolean {
  return canonicalizeText(left) === canonicalizeText(right);
}

function canonicalizeText(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/\r/g, '')
    .replace(/[ \t]+/g, ' ')
    .replace(/\n{2,}/g, '\n')
    .trim();
}

function describeAppliedChanges(
  summaryChanged: boolean,
  descriptionChanged: boolean,
  commentAdded: boolean
): string {
  if (summaryChanged && descriptionChanged && commentAdded) {
    return 'summary, description, and comment updated';
  }

  if (summaryChanged && descriptionChanged) {
    return 'summary and description updated';
  }

  if (descriptionChanged && commentAdded) {
    return 'description refreshed and comment added';
  }

  if (summaryChanged && commentAdded) {
    return 'summary updated and comment added';
  }

  if (descriptionChanged) {
    return 'description refreshed';
  }

  if (summaryChanged) {
    return 'summary updated';
  }

  return 'comment added';
}
