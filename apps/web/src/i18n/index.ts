import { en, ru, uz } from '@xavfsizmi/i18n-data';
import i18next from 'i18next';
import { initReactI18next } from 'react-i18next';

import type { Locale } from './detect';
import { detectLocale, SUPPORTED_LOCALES } from './detect';

export const i18n = i18next.createInstance();

void i18n.use(initReactI18next).init({
  resources: {
    uz: { common: uz },
    ru: { common: ru },
    en: { common: en },
  },
  lng: detectLocale(),
  fallbackLng: 'uz',
  defaultNS: 'common',
  supportedLngs: SUPPORTED_LOCALES as unknown as string[],
  interpolation: { escapeValue: false },
  returnNull: false,
});

export type { Locale };
