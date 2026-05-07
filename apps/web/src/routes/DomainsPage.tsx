import { useState } from 'react';
import { useTranslation } from 'react-i18next';

interface MethodCardProps {
  title: string;
  body: string;
  index: number;
}

function MethodCard({ title, body, index }: MethodCardProps) {
  return (
    <article className="rounded-lg border border-slate-200 bg-white p-5">
      <p className="text-xs font-semibold uppercase tracking-wide text-brand">#{index}</p>
      <h3 className="mt-1 text-lg font-semibold text-slate-900">{title}</h3>
      <p className="mt-2 text-sm text-slate-600">{body}</p>
    </article>
  );
}

export function DomainsPage() {
  const { t } = useTranslation();
  const [domain, setDomain] = useState('');

  return (
    <section className="mx-auto max-w-4xl px-4 py-12">
      <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">{t('domains.title')}</h1>
      <p className="mt-3 text-slate-600">{t('domains.subtitle')}</p>

      <form
        onSubmit={(e) => e.preventDefault()}
        className="mt-6 flex flex-col gap-3 sm:flex-row"
        aria-label="domain"
      >
        <label className="sr-only" htmlFor="domain-input">
          {t('domains.placeholder')}
        </label>
        <input
          id="domain-input"
          type="text"
          value={domain}
          onChange={(e) => setDomain(e.target.value)}
          placeholder={t('domains.placeholder')}
          className="flex-1 rounded border border-slate-300 px-4 py-3 text-base shadow-sm focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
        />
        <button
          type="submit"
          disabled
          className="rounded bg-brand px-6 py-3 font-semibold text-white shadow-sm hover:bg-brand-dark disabled:opacity-60"
        >
          {t('domains.cta')}
        </button>
      </form>
      <p className="mt-3 text-sm text-slate-500">{t('domains.coming_soon')}</p>

      <div className="mt-10">
        <h2 className="text-xl font-semibold text-slate-900">{t('domains.verification_title')}</h2>
        <p className="mt-2 text-sm text-slate-600">{t('domains.verification_intro')}</p>
        <div className="mt-4 grid gap-4 sm:grid-cols-3">
          <MethodCard
            title={t('domains.method_dns_title')}
            body={t('domains.method_dns_body')}
            index={1}
          />
          <MethodCard
            title={t('domains.method_email_title')}
            body={t('domains.method_email_body')}
            index={2}
          />
          <MethodCard
            title={t('domains.method_meta_title')}
            body={t('domains.method_meta_body')}
            index={3}
          />
        </div>
      </div>
    </section>
  );
}
