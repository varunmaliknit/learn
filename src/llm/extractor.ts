import OpenAI from 'openai';
import { z } from 'zod';
import type { Config } from '../config.js';

const looseExtractionSchema = z.object({
  decision: z.string().min(1).nullable().optional(),
  summary: z.string().min(1).nullable().optional(),
  description: z.string().min(1).nullable().optional(),
  issueType: z.string().min(1).nullable().optional(),
  priority: z.string().nullable().optional()
});

export interface IssueExtraction {
  decision: 'create' | 'update' | 'ignore';
  summary: string;
  description: string;
  issueType: 'Task' | 'Bug' | 'Story';
  priority: 'Lowest' | 'Low' | 'Medium' | 'High' | 'Highest' | null;
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
