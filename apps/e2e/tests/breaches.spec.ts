import { expect, test } from '@playwright/test';
import { mockApi, SAMPLE_BREACH } from './_helpers';

test.describe('All Breaches page', () => {
  test.beforeEach(async ({ page }) => {
    await mockApi(page, { allBreaches: [SAMPLE_BREACH] });
  });

  test('renders breach list', async ({ page }) => {
    await page.goto('/en/breaches');
    await expect(page.locator('h1')).toContainText('breach');
    await expect(page.locator('h3', { hasText: 'Adobe' })).toBeVisible();
  });

  test('clicking a breach navigates to its detail', async ({ page }) => {
    await page.goto('/en/breaches');
    await page.locator('a', { hasText: 'Adobe' }).first().click();
    await page.waitForURL('**/breach/Adobe');
  });
});
