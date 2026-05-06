export type CommandIntent = 'create' | 'update' | 'ignore';

export interface ParsedCommand {
  intent: CommandIntent;
  normalizedText: string;
  jiraIssueKey: string | null;
}

const slackMentionPattern = /<@[A-Z0-9]+>/gi;
const whitespacePattern = /\s+/g;

export function normalizeCommandText(text: string): string {
  return text
    .replace(slackMentionPattern, '')
    .replace(/[“”]/g, '"')
    .replace(/[‘’]/g, "'")
    .toLowerCase()
    .replace(whitespacePattern, ' ')
    .trim();
}

export function parseCommand(text: string): ParsedCommand {
  const normalizedText = normalizeCommandText(text);
  const jiraIssueKey = extractJiraIssueKey(normalizedText);
  const shouldCreate =
    /\bcreate\s+(a\s+)?ticket\b/.test(normalizedText) ||
    /\btrack\s+this\b/.test(normalizedText);
  const shouldUpdate =
    /\bupdate\s+(the\s+)?ticket\b/.test(normalizedText) ||
    /\bupdate\s+this\b/.test(normalizedText) ||
    /\bupdate\s+jira\b/.test(normalizedText);

  return {
    intent: shouldCreate ? 'create' : shouldUpdate ? 'update' : 'ignore',
    normalizedText,
    jiraIssueKey
  };
}

function extractJiraIssueKey(text: string): string | null {
  const match = text.match(/\b([a-z][a-z0-9_]*-\d+)\b/i);
  return match?.[1]?.toUpperCase() ?? null;
}
