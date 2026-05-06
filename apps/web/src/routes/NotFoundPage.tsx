import { useTranslation } from 'react-i18next';
import { Link, useParams } from 'react-router';

export function NotFoundPage() {
  const { t } = useTranslation();
  const { locale = 'uz' } = useParams();
  return (
    <section className="mx-auto max-w-xl px-4 py-24 text-center">
      <h1 className="text-5xl font-bold">404</h1>
      <p className="mt-4 text-lg text-slate-600">{t('not_found.message')}</p>
      <Link
        to={`/${locale}`}
        className="mt-8 inline-block rounded bg-brand px-5 py-2 font-semibold text-white"
      >
        {t('not_found.home')}
      </Link>
    </section>
  );
}
