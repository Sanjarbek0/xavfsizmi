import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { AccountLookupResponse } from '@xavfsizmi/shared-types';

import { ApiError, lookupAccount } from '../lib/api';
import { BreachCard } from '../components/BreachCard';

type State =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ok'; result: AccountLookupResponse }
  | { status: 'error'; message: string };

function describeError(err: unknown, t: (k: string) => string): string {
  if (err instanceof ApiError) {
    if (err.status === 429) return t('errors.rate_limited');
    return err.message || t('errors.unknown');
  }
  if (err instanceof TypeError) return t('errors.network');
  return t('errors.unknown');
}

export function HomePage() {
  const { t } = useTranslation();
  const [email, setEmail] = useState('');
  const [state, setState] = useState<State>({ status: 'idle' });

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const value = email.trim();
    if (!value) return;
    setState({ status: 'loading' });
    try {
      const result = await lookupAccount(value);
      setState({ status: 'ok', result });
    } catch (err) {
      setState({ status: 'error', message: describeError(err, t) });
    }
  }

  return (
    <section className="mx-auto max-w-3xl px-4 py-12 sm:py-16">
      <h1 className="text-balance text-4xl font-bold tracking-tight sm:text-5xl">
        {t('home.title')}
      </h1>
      <p className="mt-4 text-lg text-slate-600">{t('home.subtitle')}</p>

      <form onSubmit={onSubmit} className="mt-8 flex flex-col gap-3 sm:flex-row">
        <label className="sr-only" htmlFor="account-email">
          {t('home.email_placeholder')}
        </label>
        <input
          id="account-email"
          type="email"
          required
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder={t('home.email_placeholder')}
          className="flex-1 rounded border border-slate-300 px-4 py-3 text-base shadow-sm focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
        />
        <button
          type="submit"
          disabled={state.status === 'loading'}
          className="rounded bg-brand px-6 py-3 font-semibold text-white shadow-sm hover:bg-brand-dark disabled:opacity-60"
        >
          {state.status === 'loading' ? t('home.checking') : t('home.cta')}
        </button>
      </form>

      <div className="mt-8 space-y-6" aria-live="polite">
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
          <>
            <div className="rounded border border-amber-300 bg-amber-50 p-4 text-amber-900">
              <p className="font-semibold">
                {state.result.breaches.length === 1
                  ? t('home.result.found_one')
                  : t('home.result.found_many', { count: state.result.breaches.length })}
              </p>
            </div>
            <div className="grid gap-4">
              {state.result.breaches.map((b) => (
                <BreachCard key={b.name} breach={b} href />
              ))}
            </div>
            <div className="rounded border border-slate-200 bg-slate-50 p-4">
              <p className="font-semibold text-slate-800">{t('home.result.next_steps_title')}</p>
              <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm text-slate-700">
                <li>{t('home.result.next_step_1')}</li>
                <li>{t('home.result.next_step_2')}</li>
                <li>{t('home.result.next_step_3')}</li>
              </ol>
            </div>
          </>
        )}
      </div>

      <section className="mt-12 rounded-lg border border-slate-200 bg-white p-6">
        <h2 className="text-lg font-semibold text-slate-900">{t('home.trust.title')}</h2>
        <ul className="mt-3 space-y-2 text-sm text-slate-700">
          <li>• {t('home.trust.k_anonymity')}</li>
          <li>• {t('home.trust.no_sale')}</li>
          <li>• {t('home.trust.open_design')}</li>
        </ul>
      </section>
    </section>
  );
}
