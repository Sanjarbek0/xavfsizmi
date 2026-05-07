import { useTranslation } from 'react-i18next';

export function SecurityPage() {
  const { t } = useTranslation();
  return (
    <article className="prose mx-auto max-w-3xl px-4 py-16">
      <h1>{t('security.title')}</h1>
      <p>{t('security.intro')}</p>
      <h2>{t('security.k_anonymity.title')}</h2>
      <p>{t('security.k_anonymity.body')}</p>
      <h2>{t('security.transport.title')}</h2>
      <p>{t('security.transport.body')}</p>
      <h2>{t('security.storage.title')}</h2>
      <p>{t('security.storage.body')}</p>
      <h2>{t('security.rate_limits.title')}</h2>
      <p>{t('security.rate_limits.body')}</p>
    </article>
  );
}
