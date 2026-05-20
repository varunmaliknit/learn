import { describe, expect, it } from 'vitest';
import { buildThreadTranscript } from '../src/slack/threadService.js';

describe('buildThreadTranscript edge cases', () => {
  it('returns empty string for an empty array', () => {
    expect(buildThreadTranscript([])).toBe('');
  });

  it('uses "unknown" when user, username, and bot_id are all missing', () => {
    const transcript = buildThreadTranscript([
      { ts: '1.0', text: 'Hello from nowhere' }
    ]);
    expect(transcript).toBe('[unknown] Hello from nowhere');
  });

  it('prefers user over username and bot_id', () => {
    const transcript = buildThreadTranscript([
      { ts: '1.0', user: 'U1', username: 'alice', bot_id: 'B1', text: 'Hi' }
    ]);
    expect(transcript).toBe('[U1] Hi');
  });

  it('falls back to username when user is missing', () => {
    const transcript = buildThreadTranscript([
      { ts: '1.0', username: 'webhook-bot', text: 'Deployed' }
    ]);
    expect(transcript).toBe('[webhook-bot] Deployed');
  });

  it('falls back to bot_id when user and username are missing', () => {
    const transcript = buildThreadTranscript([
      { ts: '1.0', bot_id: 'B99', text: 'Automated message' }
    ]);
    expect(transcript).toBe('[B99] Automated message');
  });

  it('filters out messages with undefined text', () => {
    const transcript = buildThreadTranscript([
      { ts: '1.0', user: 'U1' },
      { ts: '2.0', user: 'U2', text: 'Real content' }
    ]);
    expect(transcript).toBe('[U2] Real content');
  });

  it('filters out messages where text is only whitespace', () => {
    const transcript = buildThreadTranscript([
      { ts: '1.0', user: 'U1', text: '   \t\n  ' },
      { ts: '2.0', user: 'U2', text: 'Actual text' }
    ]);
    expect(transcript).toBe('[U2] Actual text');
  });

  it('collapses internal whitespace (tabs, newlines) to single spaces', () => {
    const transcript = buildThreadTranscript([
      { ts: '1.0', user: 'U1', text: 'line1\n\nline2\t\ttab' }
    ]);
    expect(transcript).toBe('[U1] line1 line2 tab');
  });

  it('trims leading and trailing whitespace from text', () => {
    const transcript = buildThreadTranscript([
      { ts: '1.0', user: 'U1', text: '  padded text  ' }
    ]);
    expect(transcript).toBe('[U1] padded text');
  });

  it('handles a single message', () => {
    const transcript = buildThreadTranscript([
      { ts: '1.0', user: 'U1', text: 'Only message' }
    ]);
    expect(transcript).toBe('[U1] Only message');
  });

  it('filters out ALL messages that result in empty text after sanitization', () => {
    const transcript = buildThreadTranscript([
      { ts: '1.0', user: 'U1', text: '' },
      { ts: '2.0', user: 'U2', text: '' }
    ]);
    expect(transcript).toBe('');
  });

  it('preserves input order (does not sort by timestamp)', () => {
    const messages = [
      { ts: '3.0', user: 'U3', text: 'Third' },
      { ts: '1.0', user: 'U1', text: 'First' },
      { ts: '2.0', user: 'U2', text: 'Second' }
    ];
    const transcript = buildThreadTranscript(messages);
    expect(transcript).toBe(
      '[U3] Third\n[U1] First\n[U2] Second'
    );
  });

  it('handles messages with equal timestamps', () => {
    const transcript = buildThreadTranscript([
      { ts: '1.0', user: 'U1', text: 'A' },
      { ts: '1.0', user: 'U2', text: 'B' }
    ]);
    expect(transcript).toContain('[U1] A');
    expect(transcript).toContain('[U2] B');
  });

  it('preserves special characters in message text', () => {
    const transcript = buildThreadTranscript([
      { ts: '1.0', user: 'U1', text: '<https://example.com|link> & "quotes"' }
    ]);
    expect(transcript).toBe('[U1] <https://example.com|link> & "quotes"');
  });
});
