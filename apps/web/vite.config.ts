/// <reference types="vitest" />
import react from '@vitejs/plugin-react';
import { defineConfig, type UserConfig } from 'vite';

const config: UserConfig & { test: Record<string, unknown> } = {
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/v1': 'http://localhost:8000',
      '/api/passwords': 'http://localhost:8787',
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
  },
};

export default defineConfig(config);
