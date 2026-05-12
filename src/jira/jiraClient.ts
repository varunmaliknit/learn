import type { Config } from '../config.js';

export type JiraIssueType = 'Task' | 'Bug' | 'Story';
export type JiraPriority = 'Lowest' | 'Low' | 'Medium' | 'High' | 'Highest';

export interface CreateJiraIssueInput {
  summary: string;
  description: string;
  issueType: JiraIssueType;
  priority: JiraPriority | null;
}

export interface JiraIssue {
  id: string;
  key: string;
  url: string;
}

export interface JiraIssueDetails extends JiraIssue {
  summary: string;
  description: string;
  recentComments: string[];
}

interface JiraIssueResponse {
  id: string;
  key: string;
  fields?: {
    summary?: string | null;
    description?: unknown;
    comment?: {
      comments?: Array<{
        body?: unknown;
      }>;
    };
  };
}

interface JiraProjectResponse {
  issueTypes?: JiraProjectIssueType[];
}

interface JiraProjectIssueType {
  id: string;
  name: string;
  subtask?: boolean;
}

export class JiraClient {
  private readonly authHeader: string;
  private projectIssueTypesCache: JiraProjectIssueType[] | null = null;

  public constructor(private readonly config: Config) {
    this.authHeader = `Basic ${Buffer.from(
      `${config.JIRA_USER_EMAIL}:${config.JIRA_API_TOKEN}`
    ).toString('base64')}`;
  }

  public async createIssue(input: CreateJiraIssueInput): Promise<JiraIssue> {
    const resolvedIssueType = await this.resolveIssueTypeName(input.issueType);
    const fields: Record<string, unknown> = {
      project: { key: this.config.JIRA_PROJECT_KEY },
      summary: input.summary,
      description: toAtlassianDocument(input.description),
      issuetype: { name: resolvedIssueType }
    };

    if (input.priority) {
      fields.priority = { name: input.priority };
    }

    const issue = await this.request<JiraIssueResponse>('/rest/api/3/issue', {
      method: 'POST',
      body: JSON.stringify({ fields })
    });

    return {
      id: issue.id,
      key: issue.key,
      url: this.issueUrl(issue.key)
    };
  }

  public async addComment(issueKey: string, body: string): Promise<void> {
    await this.request(`/rest/api/3/issue/${encodeURIComponent(issueKey)}/comment`, {
      method: 'POST',
      body: JSON.stringify({
        body: toAtlassianDocument(body)
      })
    });
  }

  public async getIssue(issueKey: string): Promise<JiraIssueDetails> {
    const issue = await this.request<JiraIssueResponse>(
      `/rest/api/3/issue/${encodeURIComponent(issueKey)}`,
      {
        method: 'GET'
      }
    );

    return {
      id: issue.id,
      key: issue.key,
      url: this.issueUrl(issue.key),
      summary: issue.fields?.summary?.trim() || issue.key,
      description: fromAtlassianDocument(issue.fields?.description),
      recentComments: (issue.fields?.comment?.comments ?? [])
        .slice(-5)
        .map((comment) => fromAtlassianDocument(comment.body))
        .filter((body) => body.length > 0)
    };
  }

  public async updateIssue(
    issueKey: string,
    input: { summary?: string; description?: string }
  ): Promise<void> {
    const fields: Record<string, unknown> = {};

    if (typeof input.summary === 'string') {
      fields.summary = input.summary;
    }

    if (typeof input.description === 'string') {
      fields.description = toAtlassianDocument(input.description);
    }

    if (Object.keys(fields).length === 0) {
      return;
    }

    await this.request(`/rest/api/3/issue/${encodeURIComponent(issueKey)}`, {
      method: 'PUT',
      body: JSON.stringify({ fields })
    });
  }

  public issueUrl(issueKey: string): string {
    return `${this.config.JIRA_BASE_URL}/browse/${issueKey}`;
  }

  private async resolveIssueTypeName(requestedType: JiraIssueType): Promise<string> {
    const availableTypes = await this.getProjectIssueTypes();
    if (availableTypes.length === 0) {
      return requestedType;
    }

    const preferredNames = issueTypeCandidates(requestedType);
    for (const preferredName of preferredNames) {
      const match = availableTypes.find(
        (issueType) => normalizeIssueTypeName(issueType.name) === normalizeIssueTypeName(preferredName)
      );
      if (match) {
        return match.name;
      }
    }

    const fallbackType = availableTypes.find((issueType) => !issueType.subtask) ?? availableTypes[0];
    if (!fallbackType) {
      return requestedType;
    }

    return fallbackType.name;
  }

  private async getProjectIssueTypes(): Promise<JiraProjectIssueType[]> {
    if (this.projectIssueTypesCache) {
      return this.projectIssueTypesCache;
    }

    const project = await this.request<JiraProjectResponse>(
      `/rest/api/3/project/${encodeURIComponent(this.config.JIRA_PROJECT_KEY)}?expand=issueTypes`,
      {
        method: 'GET'
      }
    );

    this.projectIssueTypesCache = project.issueTypes ?? [];
    return this.projectIssueTypesCache;
  }

  private async request<T = unknown>(path: string, init: RequestInit): Promise<T> {
    const response = await fetch(`${this.config.JIRA_BASE_URL}${path}`, {
      ...init,
      headers: {
        Authorization: this.authHeader,
        Accept: 'application/json',
        'Content-Type': 'application/json',
        ...init.headers
      }
    });

    if (!response.ok) {
      const body = await response.text();
      throw new Error(`Jira API request failed: ${response.status} ${response.statusText} ${body}`);
    }

    if (response.status === 204) {
      return undefined as T;
    }

    return (await response.json()) as T;
  }
}

function toAtlassianDocument(text: string): unknown {
  const lines = text.split('\n');

  return {
    type: 'doc',
    version: 1,
    content: lines.map((line) => ({
      type: 'paragraph',
      content: line ? [{ type: 'text', text: line }] : []
    }))
  };
}

function fromAtlassianDocument(value: unknown): string {
  if (!value || typeof value !== 'object') {
    return '';
  }

  const lines = extractTextSegments(value);
  return lines.join('\n').trim();
}

function extractTextSegments(node: unknown): string[] {
  if (!node || typeof node !== 'object') {
    return [];
  }

  const record = node as {
    type?: string;
    text?: string;
    content?: unknown[];
  };

  if (record.type === 'text' && typeof record.text === 'string') {
    return [record.text];
  }

  const content = Array.isArray(record.content) ? record.content : [];
  const childText = content.flatMap((child) => extractTextSegments(child));

  if (record.type === 'paragraph' || record.type === 'listItem') {
    const joined = childText.join('').trim();
    return joined ? [joined] : [];
  }

  if (record.type === 'bulletList' || record.type === 'orderedList' || record.type === 'doc') {
    return childText;
  }

  return childText;
}

function issueTypeCandidates(requestedType: JiraIssueType): string[] {
  switch (requestedType) {
    case 'Bug':
      return ['Bug', 'Defect', 'Incident', 'Problem'];
    case 'Story':
      return ['Story', 'User Story', 'Feature', 'Enhancement', 'Change'];
    case 'Task':
      return ['Task', 'Work Item', 'Ticket', 'Service Request'];
  }
}

function normalizeIssueTypeName(value: string): string {
  return value.trim().toLowerCase().replace(/\s+/g, ' ');
}
