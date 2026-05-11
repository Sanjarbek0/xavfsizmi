import type { Page, Route } from '@playwright/test';

/** Raw shape the API actually returns (snake_case, lowercased). */
export interface RawBreach {
  name: string;
  title?: string | null;
  domain?: string | null;
  breach_date?: string | null;
  pwn_count?: number | null;
  is_verified?: boolean | null;
  is_sensitive?: boolean | null;
  is_fabricated?: boolean | null;
  is_retired?: boolean | null;
  is_spam_list?: boolean | null;
  description?: string | null;
  data_classes?: string[] | null;
  logo_path?: string | null;
}

/** Default fixtures the web app expects from the API. */
export interface ApiFixtures {
  me?: { user: { id: string; email: string; is_admin: boolean } } | null;
  /** Breaches returned by ``POST /v1/breaches/account``. */
  accountLookup?: { email: string; breaches: RawBreach[]; cached?: boolean };
  /** Breaches returned by ``GET /v1/breaches``. */
  allBreaches?: RawBreach[];
  /** Body returned by the Cloudflare Worker. */
  passwordsRange?: string;
}

/**
 * Install ``page.route`` handlers for every endpoint the web app calls. Tests
 * stay decoupled from the FastAPI server.
 */
export async function mockApi(page: Page, fx: ApiFixtures = {}): Promise<void> {
  await page.route('**/v1/auth/me', async (route: Route) => {
    if (fx.me) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(fx.me),
      });
    } else {
      await route.fulfill({
        status: 401,
        contentType: 'application/problem+json',
        body: JSON.stringify({ status: 401, title: 'Unauthorized', detail: 'auth.session_required' }),
      });
    }
  });

  await page.route('**/v1/breaches/account', async (route: Route) => {
    const payload = fx.accountLookup ?? {
      email: '',
      breaches: [],
    };
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(payload),
    });
  });

  await page.route('**/v1/breaches/paste', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ email: '', pastes: [] }),
    });
  });

  await page.route(/\/v1\/breaches(\?.*)?$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(fx.allBreaches ?? []),
    });
  });

  await page.route(/\/v1\/breaches\/(?!account|paste)([^/?]+)/, async (route: Route) => {
    const url = new URL(route.request().url());
    const name = decodeURIComponent(url.pathname.split('/').pop() ?? '');
    const match = (fx.allBreaches ?? []).find((b) => b.name === name);
    if (match) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(match),
      });
    } else {
      await route.fulfill({
        status: 404,
        contentType: 'application/problem+json',
        body: JSON.stringify({ status: 404, title: 'Not found' }),
      });
    }
  });

  await page.route('**/api/passwords/range/**', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'text/plain',
      body: fx.passwordsRange ?? '0000000000000000000000000000000000000:0\n',
    });
  });
}

/** Sample breach payload matching the API's snake_case shape. */
export const SAMPLE_BREACH: RawBreach = {
  name: 'Adobe',
  title: 'Adobe',
  domain: 'adobe.com',
  breach_date: '2013-10-04',
  pwn_count: 152445165,
  description: 'In October 2013, 153 million Adobe accounts were breached.',
  data_classes: ['Email addresses', 'Password hints', 'Passwords', 'Usernames'],
  is_verified: true,
  is_fabricated: false,
  is_sensitive: false,
  is_retired: false,
  is_spam_list: false,
  logo_path: '',
};
