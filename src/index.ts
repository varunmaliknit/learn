import { createHttpApp } from './app.js';
import { loadConfig } from './config.js';
import { prisma } from './db/prisma.js';
import { JiraClient } from './jira/jiraClient.js';
import { LlmExtractor } from './llm/extractor.js';
import { logger } from './logger.js';
import { createSlackApp } from './slack/slackApp.js';
import { IdempotencyService } from './services/idempotencyService.js';
import { ThreadLinkService } from './services/threadLinkService.js';

async function main(): Promise<void> {
  const config = loadConfig();

  await prisma.$connect();

  const threadLinkService = new ThreadLinkService(prisma);
  const idempotencyService = new IdempotencyService(prisma);
  const jiraClient = new JiraClient(config);
  const llmExtractor = new LlmExtractor(config);

  const httpApp = createHttpApp();
  const server = httpApp.listen(config.PORT, () => {
    logger.info({ port: config.PORT }, 'Health server listening');
  });

  const slackApp = createSlackApp({
    config,
    threadLinkService,
    idempotencyService,
    jiraClient,
    llmExtractor
  });

  await slackApp.start();
  logger.info('Slack Bolt app started in Socket Mode');

  const shutdown = async (signal: string): Promise<void> => {
    logger.info({ signal }, 'Shutting down');
    server.close();
    await slackApp.stop();
    await prisma.$disconnect();
    process.exit(0);
  };

  process.on('SIGTERM', () => {
    void shutdown('SIGTERM');
  });
  process.on('SIGINT', () => {
    void shutdown('SIGINT');
  });
}

main().catch(async (error: unknown) => {
  logger.fatal({ err: error }, 'Service failed to start');
  await prisma.$disconnect();
  process.exit(1);
});
