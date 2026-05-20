import { describe, expect, it } from 'vitest';
import { normalizeCommandText, parseCommand } from '../src/slack/commandParser.js';

describe('commandParser edge cases', () => {
  describe('normalizeCommandText', () => {
    it('returns empty string for empty input', () => {
      expect(normalizeCommandText('')).toBe('');
    });

    it('returns empty string for whitespace-only input', () => {
      expect(normalizeCommandText('   \t\n  ')).toBe('');
    });

    it('returns empty string when input is only a Slack mention', () => {
      expect(normalizeCommandText('<@U123ABC>')).toBe('');
    });

    it('strips multiple Slack mentions', () => {
      expect(normalizeCommandText('<@U111> <@U222> hello')).toBe('hello');
    });

    it('normalizes curly double quotes to straight', () => {
      expect(normalizeCommandText('\u201CHello\u201D')).toBe('"hello"');
    });

    it('normalizes curly single quotes to straight', () => {
      expect(normalizeCommandText('\u2018it\u2019s')).toBe("'it's");
    });

    it('collapses tabs and mixed whitespace', () => {
      expect(normalizeCommandText('hello\t\tworld')).toBe('hello world');
    });

    it('collapses newlines into single spaces', () => {
      expect(normalizeCommandText('hello\nworld\nfoo')).toBe('hello world foo');
    });
  });

  describe('parseCommand', () => {
    it('returns ignore for empty string', () => {
      const parsed = parseCommand('');
      expect(parsed.intent).toBe('ignore');
      expect(parsed.normalizedText).toBe('');
      expect(parsed.jiraIssueKey).toBeNull();
    });

    it('returns ignore for whitespace-only input', () => {
      expect(parseCommand('   ').intent).toBe('ignore');
    });

    it('returns ignore for a mention-only message', () => {
      expect(parseCommand('<@UBOT123>').intent).toBe('ignore');
    });

    it('prioritizes create over update when both keywords appear', () => {
      const parsed = parseCommand('<@U123> create ticket and update ticket');
      expect(parsed.intent).toBe('create');
    });

    it('detects "create a ticket" with the article', () => {
      expect(parseCommand('create a ticket').intent).toBe('create');
    });

    it('detects "update the ticket" with the article', () => {
      expect(parseCommand('update the ticket').intent).toBe('update');
    });

    it('detects "update jira" as update intent', () => {
      expect(parseCommand('<@U123> update jira').intent).toBe('update');
    });

    it('is case-insensitive for create commands', () => {
      expect(parseCommand('CREATE TICKET').intent).toBe('create');
      expect(parseCommand('Create Ticket').intent).toBe('create');
    });

    it('is case-insensitive for update commands', () => {
      expect(parseCommand('UPDATE TICKET').intent).toBe('update');
      expect(parseCommand('Update This').intent).toBe('update');
    });

    it('extracts Jira key with underscores in the project key', () => {
      const parsed = parseCommand('update ticket MY_PROJECT-42');
      expect(parsed.jiraIssueKey).toBe('MY_PROJECT-42');
    });

    it('extracts first Jira key when multiple are present', () => {
      const parsed = parseCommand('update ticket ABC-1 and DEF-2');
      expect(parsed.jiraIssueKey).toBe('ABC-1');
    });

    it('extracts Jira key regardless of case', () => {
      const parsed = parseCommand('check proj-99');
      expect(parsed.jiraIssueKey).toBe('PROJ-99');
    });

    it('does not extract a key when digits are missing', () => {
      const parsed = parseCommand('update ticket ABC-');
      expect(parsed.jiraIssueKey).toBeNull();
    });

    it('does not match a key starting with a digit', () => {
      const parsed = parseCommand('update 123-456');
      expect(parsed.jiraIssueKey).toBeNull();
    });

    it('handles "track this" with extra whitespace', () => {
      expect(parseCommand('<@U1>   track   this  ').intent).toBe('create');
    });

    it('does not match partial keywords like "created" or "tracking"', () => {
      expect(parseCommand('created a new task').intent).toBe('ignore');
      expect(parseCommand('tracking progress').intent).toBe('ignore');
    });

    it('does not match "update" without a qualifying noun', () => {
      expect(parseCommand('update me on the status').intent).toBe('ignore');
    });

    it('handles very long input without crashing', () => {
      const longText = 'a'.repeat(10_000) + ' create ticket';
      const parsed = parseCommand(longText);
      expect(parsed.intent).toBe('create');
    });

    it('handles unicode and emoji in input', () => {
      const parsed = parseCommand('🚨 create ticket for outage');
      expect(parsed.intent).toBe('create');
    });

    it('handles smart quotes around keywords', () => {
      const parsed = parseCommand('\u201Ccreate ticket\u201D');
      expect(parsed.intent).toBe('create');
    });
  });
});
