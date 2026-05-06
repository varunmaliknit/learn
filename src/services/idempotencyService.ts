import { Prisma, type PrismaClient } from '@prisma/client';

export class IdempotencyService {
  public constructor(private readonly db: PrismaClient) {}

  public async claimEvent(slackEventId: string, type: string): Promise<boolean> {
    try {
      await this.db.processedEvent.create({
        data: {
          slackEventId,
          type
        }
      });
      return true;
    } catch (error) {
      if (
        error instanceof Prisma.PrismaClientKnownRequestError &&
        error.code === 'P2002'
      ) {
        return false;
      }

      throw error;
    }
  }
}
