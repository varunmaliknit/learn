import { describe, expect, it } from 'vitest';
import {
  formatJiraDescription,
  normalizeDescriptionSections,
  parseJiraDescription
} from '../src/services/jiraDescriptionFormatter.js';

describe('jiraDescriptionFormatter', () => {
  it('formats stable Jira description sections', () => {
    const description = formatJiraDescription({
      problem: 'Payments fail after card verification.',
      impact: 'Users cannot complete checkout.',
      currentStatus: 'Issue is under investigation.',
      knownCause: 'Gateway dependency is returning 500s.',
      latestEta: 'Vendor ETA pending.',
      evidence: ['AMEX gateway returns 500'],
      actionsTaken: ['Vendor contacted'],
      nextSteps: ['Wait for vendor RCA'],
      blockers: ['External dependency on AMEX'],
      owners: ['Payments team', 'Vendor support'],
      openQuestions: ['Is this limited to AMEX cards?'],
      slackContext: ['Support thread confirms multiple customer reports']
    });

    expect(description).toContain('Problem\nPayments fail after card verification.');
    expect(description).toContain('Known Cause / Hypothesis\nGateway dependency is returning 500s.');
    expect(description).toContain('Latest ETA / Timeline\nVendor ETA pending.');
    expect(description).toContain('Evidence\n- AMEX gateway returns 500');
    expect(description).toContain('Owners / Coordination\n- Payments team');
    expect(description).toContain('Slack Context\n- Support thread confirms multiple customer reports');
  });

  it('normalizes partial sections with fallbacks', () => {
    const normalized = normalizeDescriptionSections(
      {
        problem: ' Updated understanding ',
        evidence: [' first finding ', 'first finding', '']
      },
      {
        problem: 'Old problem',
        impact: 'Old impact',
        currentStatus: 'Old status',
        knownCause: 'Old cause',
        latestEta: 'Old ETA',
        evidence: ['Old evidence'],
        actionsTaken: ['Old action'],
        nextSteps: ['Old next step'],
        blockers: ['Old blocker'],
        owners: ['Old owner'],
        openQuestions: ['Old question'],
        slackContext: ['Old context']
      }
    );

    expect(normalized.problem).toBe('Updated understanding');
    expect(normalized.impact).toBe('Old impact');
    expect(normalized.evidence).toEqual(['first finding']);
    expect(normalized.knownCause).toBe('Old cause');
  });

  it('parses a structured Jira description back into sections', () => {
    const sections = parseJiraDescription(
      'AMEX callback failure',
      [
        'Problem',
        'Users cannot complete payment.',
        '',
        'Latest ETA / Timeline',
        'AWS promised an update within 2 hours.',
        '',
        'Actions Taken',
        '- Vendor contacted',
        '',
        'Next Steps',
        '- Wait for ETA'
      ].join('\n')
    );

    expect(sections.problem).toBe('Users cannot complete payment.');
    expect(sections.latestEta).toBe('AWS promised an update within 2 hours.');
    expect(sections.actionsTaken).toEqual(['Vendor contacted']);
    expect(sections.nextSteps).toEqual(['Wait for ETA']);
  });

  it('falls back to treating legacy Jira description as the problem statement', () => {
    const sections = parseJiraDescription(
      'AMEX callback failure',
      'Users cannot complete payment. Vendor contacted.'
    );

    expect(sections.problem).toBe('Users cannot complete payment. Vendor contacted.');
    expect(sections.actionsTaken).toEqual([]);
    expect(sections.owners).toEqual([]);
  });
});
