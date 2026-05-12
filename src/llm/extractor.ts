import OpenAI from 'openai';
import { z } from 'zod';
import type { Config } from '../config.js';
import type { JiraDescriptionSections } from '../services/jiraDescriptionFormatter.js';

const looseExtractionSchema = z.object({
  decision: z.string().min(1).nullable().optional(),
  summary: z.string().min(1).nullable().optional(),
  description: z.string().min(1).nullable().optional(),
  issueType: z.string().min(1).nullable().optional(),
  priority: z.string().nullable().optional()
});

const looseSyncPlanSchema = z.object({
  decision: z.string().min(1).nullable().optional(),
  summary: z.string().min(1).nullable().optional(),
  comment: z.string().min(1).nullable().optional(),
  reasoning: z.string().min(1).nullable().optional(),
  descriptionSections: z
    .object({
      problem: z.string().min(1).nullable().optional(),
      impact: z.string().min(1).nullable().optional(),
      currentStatus: z.string().min(1).nullable().optional(),
      knownCause: z.string().min(1).nullable().optional(),
      latestEta: z.string().min(1).nullable().optional(),
      evidence: z.union([z.array(z.string()), z.string(), z.null()]).optional(),
      actionsTaken: z.union([z.array(z.string()), z.string(), z.null()]).optional(),
      nextSteps: z.union([z.array(z.string()), z.string(), z.null()]).optional(),
      blockers: z.union([z.array(z.string()), z.string(), z.null()]).optional(),
      owners: z.union([z.array(z.string()), z.string(), z.null()]).optional(),
      openQuestions: z.union([z.array(z.string()), z.string(), z.null()]).optional(),
      slackContext: z.union([z.array(z.string()), z.string(), z.null()]).optional()
    })
    .nullable()
    .optional()
});

export interface IssueExtraction {
  decision: 'create' | 'update' | 'ignore';
  summary: string;
  description: string;
  issueType: 'Task' | 'Bug' | 'Story';
  priority: 'Lowest' | 'Low' | 'Medium' | 'High' | 'Highest' | null;
}

export type SyncDecision =
  | 'no_change'
  | 'comment_only'
  | 'comment_and_description_update'
  | 'summary_description_comment_update';

export interface IssueSyncPlan {
  decision: SyncDecision;
  summary: string | null;
  descriptionSections: Partial<JiraDescriptionSections>;
  comment: string | null;
  reasoning: string;
}

export class LlmExtractor {
  private readonly client: OpenAI;
  private readonly model: string;

  public constructor(config: Config) {
    this.client = new OpenAI({
      apiKey: config.OPENAI_API_KEY
    });
    this.model = config.OPENAI_MODEL;
  }

  public async extractIssue(transcript: string): Promise<IssueExtraction> {
    const completion = await this.client.chat.completions.create({
      model: this.model,
      temperature: 0.2,
      response_format: { type: 'json_object' },
      messages: [
        {
          role: 'system',
          content:
            'Extract Jira issue details from a Slack thread. Return only strict JSON with keys: decision, summary, description, issueType, priority. issueType must be Task, Bug, or Story. priority must be Lowest, Low, Medium, High, Highest, or null.'
        },
        {
          role: 'user',
          content: `Slack thread transcript:\n\n${transcript}`
        }
      ]
    });

    const content = completion.choices[0]?.message.content;
    if (!content) {
      throw new Error('OpenAI returned an empty extraction response');
    }

    const parsed = JSON.parse(content) as unknown;
    const looseExtraction = looseExtractionSchema.parse(parsed);
    const fallbackSummary = buildFallbackSummary(transcript);
    const fallbackDescription = buildFallbackDescription(transcript);

    return {
      decision: normalizeDecision(looseExtraction.decision),
      summary: normalizeText(looseExtraction.summary) ?? fallbackSummary,
      description: normalizeText(looseExtraction.description) ?? fallbackDescription,
      issueType: normalizeIssueType(looseExtraction.issueType),
      priority: normalizePriority(looseExtraction.priority)
    };
  }

  public async planIssueSync(input: {
    transcript: string;
    jiraSummary: string;
    jiraDescription: string;
    jiraRecentComments: string[];
  }): Promise<IssueSyncPlan> {
    const completion = await this.client.chat.completions.create({
      model: this.model,
      temperature: 0.2,
      response_format: { type: 'json_object' },
      messages: [
        {
          role: 'system',
          content:
            'You compare a full Slack discussion with an existing Jira issue. Return only strict JSON with keys: decision, summary, descriptionSections, comment, reasoning. decision must be one of no_change, comment_only, comment_and_description_update, summary_description_comment_update. Return the canonical Jira summary and canonical descriptionSections that Jira should have after considering the Slack discussion and recent Jira comments. If the Jira summary should stay the same, return the existing summary text unchanged. If no Jira comment is needed, return comment as null. descriptionSections must contain: problem, impact, currentStatus, knownCause, latestEta, evidence, actionsTaken, nextSteps, blockers, owners, openQuestions, slackContext. Ground every field in the provided Jira or Slack content. If a fact is unknown, use null or an empty list. Do not write generic filler like \"under investigation\", \"further analysis required\", \"no blockers reported\", or \"no relevant updates\" unless the provided content explicitly supports it. Capture specific operational facts such as identified cause, contacted teams, ownership, and ETA when present.'
        },
        {
          role: 'user',
          content: [
            `Current Jira summary:\n${input.jiraSummary}`,
            `Current Jira description:\n${input.jiraDescription || '(empty)'}`,
            `Recent Jira comments:\n${input.jiraRecentComments.join('\n\n---\n\n') || '(none)'}`,
            `Slack thread transcript:\n${input.transcript}`
          ].join('\n\n')
        }
      ]
    });

    const content = completion.choices[0]?.message.content;
    if (!content) {
      throw new Error('OpenAI returned an empty sync response');
    }

    const parsed = JSON.parse(content) as unknown;
    const loosePlan = looseSyncPlanSchema.parse(parsed);

    return {
      decision: normalizeSyncDecision(loosePlan.decision),
      summary: normalizeText(loosePlan.summary) ?? input.jiraSummary,
      descriptionSections: normalizeDescriptionSectionPayload(loosePlan.descriptionSections),
      comment: normalizeText(loosePlan.comment),
      reasoning: normalizeText(loosePlan.reasoning) ?? 'No reasoning provided'
    };
  }
}

function normalizeDecision(value: string | null | undefined): IssueExtraction['decision'] {
  const normalized = normalizeToken(value);

  if (normalized.includes('ignore')) {
    return 'ignore';
  }

  if (normalized.includes('update')) {
    return 'update';
  }

  return 'create';
}

function normalizeIssueType(value: string | null | undefined): IssueExtraction['issueType'] {
  const normalized = normalizeToken(value);

  if (normalized.includes('bug') || normalized.includes('defect') || normalized.includes('incident')) {
    return 'Bug';
  }

  if (
    normalized.includes('story') ||
    normalized.includes('feature') ||
    normalized.includes('enhancement') ||
    normalized.includes('user story')
  ) {
    return 'Story';
  }

  return 'Task';
}

function normalizePriority(value: string | null | undefined): IssueExtraction['priority'] {
  if (!value) {
    return null;
  }

  const normalized = normalizeToken(value);

  if (normalized === 'null' || normalized === 'none' || normalized === 'unknown' || normalized === 'n a') {
    return null;
  }

  if (normalized.includes('highest') || normalized === 'p0' || normalized === 'sev0') {
    return 'Highest';
  }

  if (normalized.includes('high') || normalized === 'p1' || normalized === 'sev1') {
    return 'High';
  }

  if (normalized.includes('medium') || normalized.includes('med') || normalized === 'p2' || normalized === 'sev2') {
    return 'Medium';
  }

  if (normalized.includes('lowest') || normalized === 'p4' || normalized === 'sev4') {
    return 'Lowest';
  }

  if (normalized.includes('low') || normalized === 'p3' || normalized === 'sev3') {
    return 'Low';
  }

  return null;
}

function normalizeSyncDecision(value: string | null | undefined): SyncDecision {
  const normalized = normalizeToken(value);

  if (normalized.includes('summary')) {
    return 'summary_description_comment_update';
  }

  if (normalized.includes('description')) {
    return 'comment_and_description_update';
  }

  if (normalized.includes('comment')) {
    return 'comment_only';
  }

  return 'no_change';
}

function normalizeToken(value: string | null | undefined): string {
  if (!value) {
    return '';
  }

  return value
    .trim()
    .toLowerCase()
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ');
}

function normalizeText(value: string | null | undefined): string | null {
  if (!value) {
    return null;
  }

  const normalized = value.trim();
  return normalized.length > 0 ? normalized : null;
}

function normalizeDescriptionSectionPayload(
  value:
    | {
        problem?: string | null;
        impact?: string | null;
        currentStatus?: string | null;
        knownCause?: string | null;
        latestEta?: string | null;
        evidence?: string[] | string | null;
        actionsTaken?: string[] | string | null;
        nextSteps?: string[] | string | null;
        blockers?: string[] | string | null;
        owners?: string[] | string | null;
        openQuestions?: string[] | string | null;
        slackContext?: string[] | string | null;
      }
    | null
    | undefined
): Partial<JiraDescriptionSections> {
  return {
    problem: normalizeText(value?.problem),
    impact: normalizeText(value?.impact),
    currentStatus: normalizeText(value?.currentStatus),
    knownCause: normalizeText(value?.knownCause),
    latestEta: normalizeText(value?.latestEta),
    evidence: normalizeStringList(value?.evidence),
    actionsTaken: normalizeStringList(value?.actionsTaken),
    nextSteps: normalizeStringList(value?.nextSteps),
    blockers: normalizeStringList(value?.blockers),
    owners: normalizeStringList(value?.owners),
    openQuestions: normalizeStringList(value?.openQuestions),
    slackContext: normalizeStringList(value?.slackContext)
  };
}

function normalizeStringList(value: string[] | string | null | undefined): string[] {
  const items = Array.isArray(value)
    ? value
    : typeof value === 'string'
      ? splitListLikeString(value)
      : [];

  return items
    .map((item) => item.trim())
    .filter((item, index, items) => item.length > 0 && items.indexOf(item) === index);
}

function splitListLikeString(value: string): string[] {
  return value
    .split(/\n|;|•|, /)
    .map((item) => item.replace(/^- /, '').trim())
    .filter((item) => item.length > 0);
}

function buildFallbackSummary(transcript: string): string {
  const firstLine = transcript
    .split('\n')
    .map((line) => line.replace(/^\[[^\]]+\]\s*/, '').trim())
    .find((line) => line.length > 0);

  if (!firstLine) {
    return 'Slack thread follow-up';
  }

  return firstLine.slice(0, 120);
}

function buildFallbackDescription(transcript: string): string {
  return transcript.trim().length > 0 ? transcript.trim() : 'Slack thread follow-up';
}
