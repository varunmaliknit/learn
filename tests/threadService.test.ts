import { describe, expect, it } from 'vitest';
import { buildThreadTranscript } from '../src/slack/threadService.js';

describe('buildThreadTranscript', () => {
  it('formats Slack thread messages into a readable transcript', () => {
    const transcript = buildThreadTranscript([
      {
        ts: '1000.000001',
        user: 'U123',
        text: 'Checkout fails after selecting PayPal.'
      },
      {
        ts: '1000.000002',
        user: 'U456',
        text: 'I can reproduce it in production.\nNetwork tab shows a 500.'
      }
    ]);

    expect(transcript).toBe(
      '[U123] Checkout fails after selecting PayPal.\n[U456] I can reproduce it in production. Network tab shows a 500.'
    );
  });

  it('skips messages without text', () => {
    expect(
      buildThreadTranscript([
        { ts: '1000.000001', user: 'U123', text: '' },
        { ts: '1000.000002', user: 'U456', text: 'Real update' }
      ])
    ).toBe('[U456] Real update');
  });
});
