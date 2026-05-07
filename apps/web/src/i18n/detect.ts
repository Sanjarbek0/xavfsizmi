export const SUPPORTED_LOCALES = ['uz', 'ru', 'en'] as const;
export type Locale = (typeof SUPPORTED_LOCALES)[number];

const LOCALE_COOKIE = 'xv_lang';

export function isLocale(value: string | undefined): value is Locale {
  return value !== undefined && (SUPPORTED_LOCALES as readonly string[]).includes(value);
}

export function readLocaleCookie(): Locale | undefined {
  if (typeof document === 'undefined') return undefined;
  const match = document.cookie
    .split('; ')
    .map((kv) => kv.split('='))
    .find(([k]) => k === LOCALE_COOKIE);
  if (!match) return undefined;
  const value = decodeURIComponent(match[1] ?? '');
  return isLocale(value) ? value : undefined;
}

export function writeLocaleCookie(locale: Locale): void {
  if (typeof document === 'undefined') return;
  const oneYear = 60 * 60 * 24 * 365;
  document.cookie =
    `${LOCALE_COOKIE}=${encodeURIComponent(locale)}; ` +
    `Max-Age=${oneYear}; Path=/; SameSite=Lax`;
}

export function detectLocale(): Locale {
  const cookie = readLocaleCookie();
  if (cookie) return cookie;
  if (typeof navigator !== 'undefined') {
    for (const lang of navigator.languages ?? [navigator.language]) {
      const short = lang.toLowerCase().split('-')[0];
      if (isLocale(short)) return short;
    }
  }
  return 'uz';
}
