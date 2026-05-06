import express, { type Express } from 'express';
import { healthRouter } from './routes/health.js';

export function createHttpApp(): Express {
  const app = express();

  app.use(express.json());
  app.use('/health', healthRouter);

  return app;
}
