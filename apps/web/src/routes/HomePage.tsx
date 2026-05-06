import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { lookupAccount } from '../lib/api';
import type { AccountLookupResult } from '../lib/api';

export function HomePage() {
  const { t } = useTranslation();
  const [email, setEmail] = useState('');
  const [state, setState] = useState<
    | { status: 'idle' }
    | { status: 'loading' }
    | { status: 'ok'; result: AccountLookupResult }
    | { status: 'error'; message: string }
  >({ status: 'idle' });

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setState({ status: 'loading' });
    try {
      const result = await lookupAccount(email.trim());
      setState({ status: 'ok', result });
    } catch (err) {
      setState({ status: 'error', message: (err as Error).message });
    }
  }

  return (
    <section className="mx-auto max-w-2xl px-4 py-16">
      <h1 className="text-4xl font-bold tracking-tight">{t('home.title')}</h1>
      <p className="mt-3 text-lg text-slate-600">{t('home.subtitle')}</p>

      <form onSubmit={onSubmit} className="mt-8 flex flex-col gap-3 sm:flex-row">
        <input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder={t('home.email_placeholder')}
          className="flex-1 rounded border border-slate-300 px-4 py-3 text-base shadow-sm focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
        />
        <button
          type="submit"
          disabled={state.status === 'loading'}
          className="rounded bg-brand px-6 py-3 font-semibold text-white shadow-sm hover:bg-brand-dark disabled:opacity-50"
        >
          {state.status === 'loading' ? t('home.checking') : t('home.cta')}
        </button>
      </form>

      <div className="mt-8" aria-live="polite">
        {state.status === 'error' && (
          <div className="rounded border border-red-300 bg-red-50 p-4 text-red-800">
            {state.message}
          </div>
        )}
        {state.status === 'ok' && state.result.breaches.length === 0 && (
          <div className="rounded border border-emerald-300 bg-emerald-50 p-4 text-emerald-800">
            {t('home.result.clean')}
          </div>
        )}
        {state.status === 'ok' && state.result.breaches.length > 0 && (
          <div className="rounded border border-amber-300 bg-amber-50 p-4 text-amber-900">
            <p className="font-semibold">
              {t('home.result.found', { count: state.result.breaches.length })}
            </p>
            <ul className="mt-2 list-disc pl-5 text-sm">
              {state.result.breaches.map((b) => (
                <li key={b.name}>{b.title || b.name}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </section>
  );
}
