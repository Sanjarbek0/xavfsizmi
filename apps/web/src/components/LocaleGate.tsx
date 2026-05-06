import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Navigate, Outlet, useParams } from 'react-router';

import { detectLocale, isLocale, writeLocaleCookie } from '../i18n/detect';

export function LocaleGate() {
  const { locale } = useParams();
  const { i18n } = useTranslation();

  useEffect(() => {
    if (isLocale(locale) && i18n.language !== locale) {
      void i18n.changeLanguage(locale);
      writeLocaleCookie(locale);
      document.documentElement.lang = locale;
    }
  }, [locale, i18n]);

  if (!isLocale(locale)) {
    return <Navigate to={`/${detectLocale()}`} replace />;
  }
  return <Outlet />;
}
