import { useTranslation } from 'react-i18next';

export function NotificationsPage() {
  const { t } = useTranslation();
  return (
    <section className="mx-auto max-w-3xl px-4 py-16">
      <h1 className="text-3xl font-bold tracking-tight">{t('notifications.title')}</h1>
      <p className="mt-3 text-slate-600">{t('notifications.subtitle')}</p>
      <p className="mt-6 rounded border border-slate-200 bg-white p-4 text-sm text-slate-500">
        {t('common.coming_soon')}
      </p>
    </section>
  );
}
