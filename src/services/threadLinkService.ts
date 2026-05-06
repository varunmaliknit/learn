import type { PrismaClient, ThreadLink } from '@prisma/client';

export interface ThreadLinkRef {
  workspaceId: string;
  channelId: string;
  threadTs: string;
}

export interface CreateThreadLinkInput extends ThreadLinkRef {
  jiraIssueKey: string;
  jiraIssueId: string;
}

export class ThreadLinkService {
  public constructor(private readonly db: PrismaClient) {}

  public findLink(ref: ThreadLinkRef): Promise<ThreadLink | null> {
    return this.db.threadLink.findUnique({
      where: {
        workspaceId_channelId_threadTs: ref
      }
    });
  }

  public createLink(input: CreateThreadLinkInput): Promise<ThreadLink> {
    return this.db.threadLink.create({
      data: input
    });
  }
}
