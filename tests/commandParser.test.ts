import { describe, expect, it } from 'vitest';
import { normalizeCommandText, parseCommand } from '../src/slack/commandParser.js';

describe('commandParser', () => {
  it('detects create ticket mentions', () => {
    expect(parseCommand('<@U123> create ticket').intent).toBe('create');
    expect(parseCommand('<@U123> please CREATE a ticket for this').intent).toBe('create');
  });

  it('detects track this mentions and normalizes text', () => {
    expect(parseCommand('<@U123> track this').intent).toBe('create');
    expect(normalizeCommandText('<@U123>   Track   This ')).toBe('track this');
  });

  it('ignores non-ticket mentions', () => {
    expect(parseCommand('<@U123> what is the status?').intent).toBe('ignore');
  });

  it('detects update ticket commands with explicit Jira keys', () => {
    const parsed = parseCommand('<@U123> please update ticket scrum-10');

    expect(parsed.intent).toBe('update');
    expect(parsed.jiraIssueKey).toBe('SCRUM-10');
  });

  it('detects update this commands without an explicit Jira key', () => {
    const parsed = parseCommand('<@U123> update this');

    expect(parsed.intent).toBe('update');
    expect(parsed.jiraIssueKey).toBeNull();
  });
});
