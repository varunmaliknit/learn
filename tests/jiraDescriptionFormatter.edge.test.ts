import { describe, expect, it } from 'vitest';
import {
  formatJiraDescription,
  normalizeDescriptionSections,
  parseJiraDescription,
  type JiraDescriptionSections
} from '../src/services/jiraDescriptionFormatter.js';

const emptyFallback: JiraDescriptionSections = {
  problem: null,
  impact: null,
  currentStatus: null,
  knownCause: null,
  latestEta: null,
  evidence: [],
  actionsTaken: [],
  nextSteps: [],
  blockers: [],
  owners: [],
  openQuestions: [],
  slackContext: []
};

describe('formatJiraDescription edge cases', () => {
  it('returns empty string when all sections are null/empty', () => {
    expect(formatJiraDescription(emptyFallback)).toBe('');
  });

  it('omits sections with null text values', () => {
    const result = formatJiraDescription({
      ...emptyFallback,
      problem: 'Only problem'
    });
    expect(result).toBe('Problem\nOnly problem');
    expect(result).not.toContain('Impact');
    expect(result).not.toContain('Current Status');
  });

  it('omits list sections with empty arrays', () => {
    const result = formatJiraDescription({
      ...emptyFallback,
      evidence: [],
      actionsTaken: ['Did something']
    });
    expect(result).not.toContain('Evidence');
    expect(result).toContain('Actions Taken\n- Did something');
  });

  it('renders multiple list items with dash prefixes', () => {
    const result = formatJiraDescription({
      ...emptyFallback,
      nextSteps: ['Step 1', 'Step 2', 'Step 3']
    });
    expect(result).toBe('Next Steps\n- Step 1\n- Step 2\n- Step 3');
  });

  it('separates non-empty sections with double newlines', () => {
    const result = formatJiraDescription({
      ...emptyFallback,
      problem: 'A problem',
      impact: 'Some impact'
    });
    expect(result).toBe('Problem\nA problem\n\nImpact\nSome impact');
  });

  it('handles only list sections being populated', () => {
    const result = formatJiraDescription({
      ...emptyFallback,
      blockers: ['Blocker 1'],
      owners: ['Owner 1']
    });
    expect(result).toBe(
      'Blockers / Risks\n- Blocker 1\n\nOwners / Coordination\n- Owner 1'
    );
  });

  it('handles empty string as problem (falsy)', () => {
    const result = formatJiraDescription({
      ...emptyFallback,
      problem: ''
    });
    expect(result).toBe('');
  });
});

describe('parseJiraDescription edge cases', () => {
  it('returns empty sections with summary as problem for empty description', () => {
    const sections = parseJiraDescription('My Summary', '');
    expect(sections.problem).toBe('My Summary');
    expect(sections.impact).toBeNull();
    expect(sections.evidence).toEqual([]);
  });

  it('returns empty sections for whitespace-only description', () => {
    const sections = parseJiraDescription('My Summary', '   \n\t  ');
    expect(sections.problem).toBe('My Summary');
  });

  it('treats unrecognized first line as legacy description (entire text as problem)', () => {
    const sections = parseJiraDescription(
      'Title',
      'This is a free-form description without any headings.'
    );
    expect(sections.problem).toBe(
      'This is a free-form description without any headings.'
    );
  });

  it('handles consecutive headings with no content between them', () => {
    const sections = parseJiraDescription(
      'Title',
      'Problem\nImpact\nSome impact text'
    );
    expect(sections.problem).toBeNull();
    expect(sections.impact).toBe('Some impact text');
  });

  it('handles heading with only blank lines under it', () => {
    const sections = parseJiraDescription(
      'Title',
      'Problem\n\n\nImpact\nReal impact'
    );
    expect(sections.problem).toBeNull();
    expect(sections.impact).toBe('Real impact');
  });

  it('strips dash prefixes from list items', () => {
    const sections = parseJiraDescription(
      'Title',
      'Evidence\n- Item 1\n- Item 2'
    );
    expect(sections.evidence).toEqual(['Item 1', 'Item 2']);
  });

  it('handles list items without dash prefixes', () => {
    const sections = parseJiraDescription(
      'Title',
      'Evidence\nItem 1\nItem 2'
    );
    expect(sections.evidence).toEqual(['Item 1', 'Item 2']);
  });

  it('ignores unknown headings in between known headings', () => {
    const sections = parseJiraDescription(
      'Title',
      'Problem\nA bug\nRandomHeading\nSome random content\nImpact\nHigh'
    );
    expect(sections.problem).toBe('A bug\nRandomHeading\nSome random content');
    expect(sections.impact).toBe('High');
  });

  it('handles all 12 section headings', () => {
    const description = [
      'Problem', 'p',
      'Impact', 'i',
      'Current Status', 'cs',
      'Known Cause / Hypothesis', 'kc',
      'Latest ETA / Timeline', 'eta',
      'Evidence', '- e1',
      'Actions Taken', '- a1',
      'Next Steps', '- n1',
      'Blockers / Risks', '- b1',
      'Owners / Coordination', '- o1',
      'Open Questions', '- q1',
      'Slack Context', '- s1'
    ].join('\n');

    const sections = parseJiraDescription('Title', description);
    expect(sections.problem).toBe('p');
    expect(sections.impact).toBe('i');
    expect(sections.currentStatus).toBe('cs');
    expect(sections.knownCause).toBe('kc');
    expect(sections.latestEta).toBe('eta');
    expect(sections.evidence).toEqual(['e1']);
    expect(sections.actionsTaken).toEqual(['a1']);
    expect(sections.nextSteps).toEqual(['n1']);
    expect(sections.blockers).toEqual(['b1']);
    expect(sections.owners).toEqual(['o1']);
    expect(sections.openQuestions).toEqual(['q1']);
    expect(sections.slackContext).toEqual(['s1']);
  });

  it('round-trips: format then parse produces equivalent data', () => {
    const original: JiraDescriptionSections = {
      problem: 'Server is down',
      impact: 'All users affected',
      currentStatus: 'Investigating',
      knownCause: null,
      latestEta: '2 hours',
      evidence: ['Error logs show OOM'],
      actionsTaken: ['Restarted pod'],
      nextSteps: ['Increase memory limit'],
      blockers: [],
      owners: ['SRE team'],
      openQuestions: ['Is this recurring?'],
      slackContext: []
    };

    const formatted = formatJiraDescription(original);
    const parsed = parseJiraDescription('Title', formatted);

    expect(parsed.problem).toBe(original.problem);
    expect(parsed.impact).toBe(original.impact);
    expect(parsed.currentStatus).toBe(original.currentStatus);
    expect(parsed.knownCause).toBeNull();
    expect(parsed.latestEta).toBe(original.latestEta);
    expect(parsed.evidence).toEqual(original.evidence);
    expect(parsed.actionsTaken).toEqual(original.actionsTaken);
    expect(parsed.nextSteps).toEqual(original.nextSteps);
    expect(parsed.blockers).toEqual([]);
    expect(parsed.owners).toEqual(original.owners);
    expect(parsed.openQuestions).toEqual(original.openQuestions);
    expect(parsed.slackContext).toEqual([]);
  });
});

describe('normalizeDescriptionSections edge cases', () => {
  it('returns fallback entirely when partial is empty object', () => {
    const fallback: JiraDescriptionSections = {
      problem: 'Fallback problem',
      impact: 'Fallback impact',
      currentStatus: null,
      knownCause: null,
      latestEta: null,
      evidence: ['fb-evidence'],
      actionsTaken: [],
      nextSteps: [],
      blockers: [],
      owners: [],
      openQuestions: [],
      slackContext: []
    };

    const result = normalizeDescriptionSections({}, fallback);
    expect(result.problem).toBe('Fallback problem');
    expect(result.impact).toBe('Fallback impact');
    expect(result.evidence).toEqual(['fb-evidence']);
  });

  it('trims whitespace from text fields in partial', () => {
    const result = normalizeDescriptionSections(
      { problem: '  trimmed  ', impact: '\n\n' },
      emptyFallback
    );
    expect(result.problem).toBe('trimmed');
    expect(result.impact).toBeNull();
  });

  it('falls back to fallback when partial text field is empty string', () => {
    const result = normalizeDescriptionSections(
      { problem: '' },
      { ...emptyFallback, problem: 'Kept' }
    );
    expect(result.problem).toBe('Kept');
  });

  it('deduplicates list items in partial', () => {
    const result = normalizeDescriptionSections(
      { evidence: ['dup', 'dup', 'unique'] },
      emptyFallback
    );
    expect(result.evidence).toEqual(['dup', 'unique']);
  });

  it('removes empty strings from list items in partial', () => {
    const result = normalizeDescriptionSections(
      { nextSteps: ['', '  ', 'valid'] },
      emptyFallback
    );
    expect(result.nextSteps).toEqual(['valid']);
  });

  it('uses fallback list when partial list is undefined', () => {
    const result = normalizeDescriptionSections(
      {},
      { ...emptyFallback, owners: ['Fallback owner'] }
    );
    expect(result.owners).toEqual(['Fallback owner']);
  });

  it('overrides fallback list when partial provides an empty array', () => {
    const result = normalizeDescriptionSections(
      { blockers: [] },
      { ...emptyFallback, blockers: ['Old blocker'] }
    );
    expect(result.blockers).toEqual([]);
  });

  it('handles null values in partial text fields by falling back', () => {
    const result = normalizeDescriptionSections(
      { problem: null, impact: null },
      { ...emptyFallback, problem: 'FB Problem', impact: 'FB Impact' }
    );
    expect(result.problem).toBe('FB Problem');
    expect(result.impact).toBe('FB Impact');
  });

  it('trims list items and removes whitespace-only entries', () => {
    const result = normalizeDescriptionSections(
      { actionsTaken: ['  action 1  ', '   ', 'action 2'] },
      emptyFallback
    );
    expect(result.actionsTaken).toEqual(['action 1', 'action 2']);
  });
});
