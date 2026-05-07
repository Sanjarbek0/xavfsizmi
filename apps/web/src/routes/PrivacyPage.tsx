import { useTranslation } from 'react-i18next';

export function PrivacyPage() {
  const { t } = useTranslation();
  return (
    <article className="prose mx-auto max-w-3xl px-4 py-16">
      <h1>{t('privacy.title')}</h1>
      <p>{t('privacy.intro')}</p>
      <h2>{t('privacy.what_we_collect.title')}</h2>
      <p>{t('privacy.what_we_collect.body')}</p>
      <h2>{t('privacy.what_we_dont.title')}</h2>
      <p>{t('privacy.what_we_dont.body')}</p>
      <h2>{t('privacy.cookies.title')}</h2>
      <p>{t('privacy.cookies.body')}</p>
      <h2>{t('privacy.contact.title')}</h2>
      <p>{t('privacy.contact.body')}</p>
    </article>
  );
}
