import { expect, test } from '@playwright/test';
import { mockApi } from './_helpers';

test.describe('Sign-in page', () => {
  test.beforeEach(async ({ page }) => {
    await mockApi(page);
  });

  test('renders sign-in form', async ({ page }) => {
    await page.goto('/en/sign-in');
    await expect(page.locator('input[type="email"]')).toBeVisible();
    await expect(page.locator('button[type="submit"]')).toBeVisible();
  });

  test('submitting shows email-sent confirmation', async ({ page }) => {
    // Mock the magic-link request endpoint.
    await page.route('**/v1/auth/request', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true }),
      });
    });
    await page.goto('/en/sign-in');
    await page.fill('input[type="email"]', 'test@example.com');
    await page.click('button[type="submit"]');
    // "Check your inbox." is the success copy.
    await expect(page.locator('text=Check your inbox')).toBeVisible({ timeout: 5000 });
  });
});
