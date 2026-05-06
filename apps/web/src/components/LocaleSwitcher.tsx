import { useTranslation } from 'react-i18next';
import { useLocation, useNavigate, useParams } from 'react-router';

import { isLocale, SUPPORTED_LOCALES, writeLocaleCookie } from '../i18n/detect';
import type { Locale } from '../i18n/detect';

const LABELS: Record<Locale, string> = {
  uz: "O'zbekcha",
  ru: 'Русский',
  en: 'English',
};

export function LocaleSwitcher() {
  const { i18n } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const { locale: current = 'uz' } = useParams();

  function switchTo(next: Locale) {
    if (next === current) return;
    writeLocaleCookie(next);
    void i18n.changeLanguage(next);
    const restOfPath = location.pathname.replace(/^\/[^/]+/, '');
    navigate(`/${next}${restOfPath}${location.search}${location.hash}`, { replace: true });
  }

  return (
    <select
      value={isLocale(current) ? current : 'uz'}
      onChange={(e) => switchTo(e.target.value as Locale)}
      className="rounded border border-slate-300 bg-white px-2 py-1 text-sm"
      aria-label="Language"
    >
      {SUPPORTED_LOCALES.map((l) => (
        <option key={l} value={l}>
          {LABELS[l]}
        </option>
      ))}
    </select>
  );
}
