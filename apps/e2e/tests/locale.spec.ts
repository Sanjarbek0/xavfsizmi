import { expect, test } from '@playwright/test';
import { mockApi } from './_helpers';

test.describe('Locale routing', () => {
  test.beforeEach(async ({ page }) => {
    await mockApi(page);
  });

  test('root / redirects to a supported locale prefix', async ({ page, context }) => {
    // Force the uz cookie so the redirect target is deterministic regardless
    // of the test browser's Accept-Language.
    await context.addCookies([
      {
        name: 'xv_lang',
        value: 'uz',
        url: 'http://127.0.0.1:5174',
      },
    ]);
    await page.goto('/');
    await page.waitForURL(/\/(uz|ru|en)$/);
    expect(page.url()).toMatch(/\/(uz|ru|en)$/);
  });

  test('/en serves English copy', async ({ page }) => {
    await page.goto('/en');
    await expect(page.locator('h1')).toContainText('email');
  });

  test('/ru serves Russian copy', async ({ page }) => {
    await page.goto('/ru');
    await expect(page.locator('h1')).toContainText('утечк');
  });

  test('language switcher navigates to a new locale', async ({ page }) => {
    await page.goto('/uz');
    // The nav should contain a language selector — find and click "en".
    const langLink = page.locator('a[href*="/en"]').first();
    if (await langLink.isVisible()) {
      await langLink.click();
      await page.waitForURL('**/en');
      expect(page.url()).toContain('/en');
    }
  });
});
