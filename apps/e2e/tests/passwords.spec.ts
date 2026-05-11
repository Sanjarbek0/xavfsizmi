import { expect, test } from '@playwright/test';
import { mockApi } from './_helpers';

test.describe('Passwords page — k-anonymity lookup', () => {
  test.beforeEach(async ({ page }) => {
    await mockApi(page);
  });

  test('renders the password check form', async ({ page }) => {
    await page.goto('/en/passwords');
    await expect(page.locator('h1')).toContainText('password');
    await expect(page.locator('input[type="password"]')).toBeVisible();
  });

  test('shows "pwned" result for known password', async ({ page }) => {
    // SHA-1("hunter2") = F3BBBD66A63D4BF1747940578EC3D0103530E21D
    await mockApi(page, {
      passwordsRange: 'D66A63D4BF1747940578EC3D0103530E21D:42\n0000000000000000000000000000000000000:0\n',
    });
    await page.goto('/en/passwords');
    await page.fill('input[type="password"]', 'hunter2');
    await page.click('button[type="submit"]');
    await expect(page.locator('text=42')).toBeVisible();
  });

  test('shows safe result for uncompromised password', async ({ page }) => {
    // All zeros — no match
    await mockApi(page, {
      passwordsRange: '0000000000000000000000000000000000000:0\n',
    });
    await page.goto('/en/passwords');
    await page.fill('input[type="password"]', 'very-long-unlikely-passphrase-2026');
    await page.click('button[type="submit"]');
    // Should show the "safe" message — 0 times or "not found"
    await expect(page.locator('[class*="green"], [class*="emerald"]')).toBeVisible();
  });
});
