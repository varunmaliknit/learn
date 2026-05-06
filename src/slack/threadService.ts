import type { WebClient } from '@slack/web-api';

export interface SlackThreadMessage {
  ts: string;
  text?: string;
  user?: string;
  username?: string;
  bot_id?: string;
}

export interface ThreadRef {
  channelId: string;
  threadTs: string;
}

export class SlackThreadService {
  public constructor(private readonly client: WebClient) {}

  public getThreadTs(event: { ts: string; thread_ts?: string }): string {
    return event.thread_ts ?? event.ts;
  }

  public async fetchThreadMessages(ref: ThreadRef): Promise<SlackThreadMessage[]> {
    const messages: SlackThreadMessage[] = [];
    let cursor: string | undefined;

    do {
      const response = await this.client.conversations.replies({
        channel: ref.channelId,
        ts: ref.threadTs,
        cursor,
        limit: 200
      });

      messages.push(...((response.messages ?? []) as SlackThreadMessage[]));
      cursor = response.response_metadata?.next_cursor || undefined;
    } while (cursor);

    return messages.sort((a, b) => Number(a.ts) - Number(b.ts));
  }
}

export function buildThreadTranscript(messages: SlackThreadMessage[]): string {
  return messages
    .map((message) => {
      const speaker = message.user ?? message.username ?? message.bot_id ?? 'unknown';
      const text = sanitizeSlackText(message.text ?? '');
      return `[${speaker}] ${text}`;
    })
    .filter((line) => !line.endsWith('] '))
    .join('\n');
}

function sanitizeSlackText(text: string): string {
  return text.replace(/\s+/g, ' ').trim();
}
