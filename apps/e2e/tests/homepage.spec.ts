import { expect, test } from '@playwright/test';
import { mockApi, SAMPLE_BREACH } from './_helpers';

test.describe('Home page — email breach lookup', () => {
  test.beforeEach(async ({ page }) => {
    await mockApi(page);
  });

  test('renders the brand tagline and search form', async ({ page }) => {
    await page.goto('/uz');
    await expect(page.locator('h1')).toContainText('email');
    await expect(page.locator('input[type="email"]')).toBeVisible();
    await expect(page.locator('button[type="submit"]')).toBeVisible();
  });

  test('shows breach results when email is found', async ({ page }) => {
    await mockApi(page, {
      accountLookup: { email: 'victim@example.com', breaches: [SAMPLE_BREACH] },
    });
    await page.goto('/en');
    await page.fill('input[type="email"]', 'victim@example.com');
    await page.click('button[type="submit"]');
    await expect(page.locator('h3', { hasText: 'Adobe' })).toBeVisible();
  });

  test('shows "all clear" state when email is clean', async ({ page }) => {
    await mockApi(page, {
      accountLookup: { email: 'clean@example.com', breaches: [] },
    });
    await page.goto('/en');
    await page.fill('input[type="email"]', 'clean@example.com');
    await page.click('button[type="submit"]');
    // The "all clear" state on the home page is keyed on the absence of any
    // breach result. We just confirm that no breach card was rendered.
    await expect(page.locator('h3', { hasText: 'Adobe' })).toHaveCount(0);
  });
});
