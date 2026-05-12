export interface JiraDescriptionSections {
  problem: string | null;
  impact: string | null;
  currentStatus: string | null;
  knownCause: string | null;
  latestEta: string | null;
  evidence: string[];
  actionsTaken: string[];
  nextSteps: string[];
  blockers: string[];
  owners: string[];
  openQuestions: string[];
  slackContext: string[];
}

export function formatJiraDescription(sections: JiraDescriptionSections): string {
  const parts = [
    renderSection('Problem', sections.problem),
    renderSection('Impact', sections.impact),
    renderSection('Current Status', sections.currentStatus),
    renderSection('Known Cause / Hypothesis', sections.knownCause),
    renderSection('Latest ETA / Timeline', sections.latestEta),
    renderListSection('Evidence', sections.evidence),
    renderListSection('Actions Taken', sections.actionsTaken),
    renderListSection('Next Steps', sections.nextSteps),
    renderListSection('Blockers / Risks', sections.blockers),
    renderListSection('Owners / Coordination', sections.owners),
    renderListSection('Open Questions', sections.openQuestions),
    renderListSection('Slack Context', sections.slackContext)
  ].filter((part) => part.length > 0);

  return parts.join('\n\n').trim();
}

export function parseJiraDescription(
  jiraSummary: string,
  jiraDescription: string
): JiraDescriptionSections {
  const normalized = jiraDescription.trim();
  if (normalized.length === 0) {
    return emptySections(jiraSummary);
  }

  const knownHeadings = [
    'Problem',
    'Impact',
    'Current Status',
    'Known Cause / Hypothesis',
    'Latest ETA / Timeline',
    'Evidence',
    'Actions Taken',
    'Next Steps',
    'Blockers / Risks',
    'Owners / Coordination',
    'Open Questions',
    'Slack Context'
  ];

  const lines = normalized.split('\n');
  const sectionMap = new Map<string, string[]>();
  let currentHeading: string | null = null;

  for (const line of lines) {
    const trimmed = line.trim();
    if (knownHeadings.includes(trimmed)) {
      currentHeading = trimmed;
      sectionMap.set(currentHeading, []);
      continue;
    }

    if (!currentHeading) {
      return {
        ...emptySections(jiraSummary),
        problem: normalized
      };
    }

    sectionMap.get(currentHeading)?.push(trimmed);
  }

  return {
    problem: joinSectionText(sectionMap.get('Problem')),
    impact: joinSectionText(sectionMap.get('Impact')),
    currentStatus: joinSectionText(sectionMap.get('Current Status')),
    knownCause: joinSectionText(sectionMap.get('Known Cause / Hypothesis')),
    latestEta: joinSectionText(sectionMap.get('Latest ETA / Timeline')),
    evidence: normalizeList(parseSectionList(sectionMap.get('Evidence')), []),
    actionsTaken: normalizeList(parseSectionList(sectionMap.get('Actions Taken')), []),
    nextSteps: normalizeList(parseSectionList(sectionMap.get('Next Steps')), []),
    blockers: normalizeList(parseSectionList(sectionMap.get('Blockers / Risks')), []),
    owners: normalizeList(parseSectionList(sectionMap.get('Owners / Coordination')), []),
    openQuestions: normalizeList(parseSectionList(sectionMap.get('Open Questions')), []),
    slackContext: normalizeList(parseSectionList(sectionMap.get('Slack Context')), [])
  };
}

export function normalizeDescriptionSections(
  sections: Partial<JiraDescriptionSections>,
  fallback: JiraDescriptionSections
): JiraDescriptionSections {
  return {
    problem: normalizeOptionalText(sections.problem) ?? fallback.problem,
    impact: normalizeOptionalText(sections.impact) ?? fallback.impact,
    currentStatus: normalizeOptionalText(sections.currentStatus) ?? fallback.currentStatus,
    knownCause: normalizeOptionalText(sections.knownCause) ?? fallback.knownCause,
    latestEta: normalizeOptionalText(sections.latestEta) ?? fallback.latestEta,
    evidence: normalizeList(sections.evidence, fallback.evidence),
    actionsTaken: normalizeList(sections.actionsTaken, fallback.actionsTaken),
    nextSteps: normalizeList(sections.nextSteps, fallback.nextSteps),
    blockers: normalizeList(sections.blockers, fallback.blockers),
    owners: normalizeList(sections.owners, fallback.owners),
    openQuestions: normalizeList(sections.openQuestions, fallback.openQuestions),
    slackContext: normalizeList(sections.slackContext, fallback.slackContext)
  };
}

function renderSection(title: string, content: string | null): string {
  if (!content) {
    return '';
  }

  return `${title}\n${content}`;
}

function renderListSection(title: string, items: string[]): string {
  if (items.length === 0) {
    return '';
  }

  return `${title}\n${items.map((item) => `- ${item}`).join('\n')}`;
}

function normalizeOptionalText(value: string | null | undefined): string | null {
  if (!value) {
    return null;
  }

  const normalized = value.trim();
  return normalized.length > 0 ? normalized : null;
}

function normalizeList(value: string[] | undefined, fallback: string[]): string[] {
  const source = Array.isArray(value) ? value : fallback;

  return source
    .map((item) => item.trim())
    .filter((item, index, items) => item.length > 0 && items.indexOf(item) === index);
}

function emptySections(summary: string): JiraDescriptionSections {
  return {
    problem: summary,
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
}

function joinSectionText(lines: string[] | undefined): string | null {
  if (!lines || lines.length === 0) {
    return null;
  }

  const joined = lines.join('\n').trim();
  return joined.length > 0 ? joined : null;
}

function parseSectionList(lines: string[] | undefined): string[] {
  if (!lines) {
    return [];
  }

  return lines
    .map((line) => line.replace(/^- /, '').trim())
    .filter((line) => line.length > 0);
}
