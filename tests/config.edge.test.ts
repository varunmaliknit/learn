import { describe, expect, it } from 'vitest';
import { loadConfig } from '../src/config.js';

const validEnv: Record<string, string> = {
  SLACK_BOT_TOKEN: 'xoxb-test',
  SLACK_APP_TOKEN: 'xapp-test',
  SLACK_SIGNING_SECRET: 'signing-secret',
  JIRA_BASE_URL: 'https://test.atlassian.net',
  JIRA_USER_EMAIL: 'user@example.com',
  JIRA_API_TOKEN: 'jira-token',
  JIRA_PROJECT_KEY: 'PROJ',
  OPENAI_API_KEY: 'sk-test',
  OPENAI_MODEL: 'gpt-4o-mini',
  DATABASE_URL: 'postgresql://localhost:5432/test'
};

describe('loadConfig edge cases', () => {
  it('loads valid config with all required fields', () => {
    const config = loadConfig(validEnv as unknown as NodeJS.ProcessEnv);
    expect(config.SLACK_BOT_TOKEN).toBe('xoxb-test');
    expect(config.PORT).toBe(3000);
  });

  it('uses default PORT when not provided', () => {
    const config = loadConfig(validEnv as unknown as NodeJS.ProcessEnv);
    expect(config.PORT).toBe(3000);
  });

  it('uses default OPENAI_MODEL when not provided', () => {
    const env = { ...validEnv };
    delete (env as Record<string, string | undefined>).OPENAI_MODEL;
    const config = loadConfig(env as unknown as NodeJS.ProcessEnv);
    expect(config.OPENAI_MODEL).toBe('gpt-4o-mini');
  });

  it('coerces PORT string to number', () => {
    const config = loadConfig({
      ...validEnv,
      PORT: '8080'
    } as unknown as NodeJS.ProcessEnv);
    expect(config.PORT).toBe(8080);
  });

  it('throws on negative PORT', () => {
    expect(() =>
      loadConfig({
        ...validEnv,
        PORT: '-1'
      } as unknown as NodeJS.ProcessEnv)
    ).toThrow('Invalid environment configuration');
  });

  it('throws on zero PORT', () => {
    expect(() =>
      loadConfig({
        ...validEnv,
        PORT: '0'
      } as unknown as NodeJS.ProcessEnv)
    ).toThrow('Invalid environment configuration');
  });

  it('throws on non-numeric PORT', () => {
    expect(() =>
      loadConfig({
        ...validEnv,
        PORT: 'abc'
      } as unknown as NodeJS.ProcessEnv)
    ).toThrow('Invalid environment configuration');
  });

  it('throws when SLACK_BOT_TOKEN is missing', () => {
    const env = { ...validEnv };
    delete (env as Record<string, string | undefined>).SLACK_BOT_TOKEN;
    expect(() => loadConfig(env as unknown as NodeJS.ProcessEnv)).toThrow(
      'SLACK_BOT_TOKEN'
    );
  });

  it('throws when JIRA_BASE_URL is not a valid URL', () => {
    expect(() =>
      loadConfig({
        ...validEnv,
        JIRA_BASE_URL: 'not-a-url'
      } as unknown as NodeJS.ProcessEnv)
    ).toThrow('Invalid environment configuration');
  });

  it('throws when JIRA_USER_EMAIL is not a valid email', () => {
    expect(() =>
      loadConfig({
        ...validEnv,
        JIRA_USER_EMAIL: 'not-an-email'
      } as unknown as NodeJS.ProcessEnv)
    ).toThrow('Invalid environment configuration');
  });

  it('strips trailing slash from JIRA_BASE_URL', () => {
    const config = loadConfig({
      ...validEnv,
      JIRA_BASE_URL: 'https://test.atlassian.net/'
    } as unknown as NodeJS.ProcessEnv);
    expect(config.JIRA_BASE_URL).toBe('https://test.atlassian.net');
  });

  it('leaves JIRA_BASE_URL unchanged when no trailing slash', () => {
    const config = loadConfig(validEnv as unknown as NodeJS.ProcessEnv);
    expect(config.JIRA_BASE_URL).toBe('https://test.atlassian.net');
  });

  it('throws when multiple required fields are missing', () => {
    expect(() => loadConfig({} as NodeJS.ProcessEnv)).toThrow(
      'Invalid environment configuration'
    );
  });

  it('throws when OPENAI_API_KEY is empty string', () => {
    expect(() =>
      loadConfig({
        ...validEnv,
        OPENAI_API_KEY: ''
      } as unknown as NodeJS.ProcessEnv)
    ).toThrow('Invalid environment configuration');
  });

  it('throws when DATABASE_URL is empty string', () => {
    expect(() =>
      loadConfig({
        ...validEnv,
        DATABASE_URL: ''
      } as unknown as NodeJS.ProcessEnv)
    ).toThrow('Invalid environment configuration');
  });

  it('rejects PORT as a float', () => {
    expect(() =>
      loadConfig({
        ...validEnv,
        PORT: '3000.9'
      } as unknown as NodeJS.ProcessEnv)
    ).toThrow('Invalid environment configuration');
  });
});
