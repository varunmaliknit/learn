import { z } from 'zod';

const envSchema = z.object({
  SLACK_BOT_TOKEN: z.string().min(1),
  SLACK_APP_TOKEN: z.string().min(1),
  SLACK_SIGNING_SECRET: z.string().min(1),
  JIRA_BASE_URL: z.string().url(),
  JIRA_USER_EMAIL: z.string().email(),
  JIRA_API_TOKEN: z.string().min(1),
  JIRA_PROJECT_KEY: z.string().min(1),
  OPENAI_API_KEY: z.string().min(1),
  OPENAI_MODEL: z.string().min(1).default('gpt-4o-mini'),
  DATABASE_URL: z.string().min(1),
  PORT: z.coerce.number().int().positive().default(3000)
});

export type Config = z.infer<typeof envSchema>;

export function loadConfig(env: NodeJS.ProcessEnv = process.env): Config {
  const result = envSchema.safeParse(env);

  if (!result.success) {
    const message = result.error.issues
      .map((issue) => `${issue.path.join('.')}: ${issue.message}`)
      .join('\n');
    throw new Error(`Invalid environment configuration:\n${message}`);
  }

  return {
    ...result.data,
    JIRA_BASE_URL: result.data.JIRA_BASE_URL.replace(/\/$/, '')
  };
}
