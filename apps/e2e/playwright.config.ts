import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright config — runs against the locally-built web app. We boot the Vite
 * dev server via Playwright's ``webServer`` so the same config works from
 * ``pnpm --filter @xavfsizmi/e2e test`` locally *and* in CI.
 *
 * All API + worker traffic is intercepted with ``page.route`` in each test
 * (see ``tests/_helpers.ts``), so we don't need to spin up the FastAPI server
 * or the Cloudflare Worker for E2E to run.
 */
const PORT = Number(process.env.E2E_WEB_PORT ?? 5174);

export default defineConfig({
  testDir: './tests',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    // Run the web dev server from this workspace so the test runner controls
    // its lifecycle. Uses the same env shape as ``apps/web`` itself.
    command: `pnpm --filter @xavfsizmi/web exec vite preview --host 127.0.0.1 --port ${PORT} --strictPort`,
    cwd: '../..',
    url: `http://127.0.0.1:${PORT}`,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    stdout: 'pipe',
    stderr: 'pipe',
  },
});
