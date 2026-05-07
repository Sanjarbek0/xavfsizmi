import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { BreachSummary } from '@xavfsizmi/shared-types';

import { ApiError, listBreaches } from '../lib/api';
import { BreachCard } from '../components/BreachCard';

type State =
  | { status: 'loading' }
  | { status: 'ok'; breaches: BreachSummary[] }
  | { status: 'error'; message: string };

export function BreachesPage() {
  const { t } = useTranslation();
  const [state, setState] = useState<State>({ status: 'loading' });
  const [filter, setFilter] = useState('');

  useEffect(() => {
    let cancelled = false;
    setState({ status: 'loading' });
    listBreaches()
      .then((breaches) => {
        if (cancelled) return;
        const sorted = [...breaches].sort((a, b) => {
          const at = (a.title || a.name).toLowerCase();
          const bt = (b.title || b.name).toLowerCase();
          return at.localeCompare(bt);
        });
        setState({ status: 'ok', breaches: sorted });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        let message = t('errors.unknown');
        if (err instanceof ApiError) {
          message = err.status === 429 ? t('errors.rate_limited') : err.message;
        } else if (err instanceof TypeError) {
          message = t('errors.network');
        }
        setState({ status: 'error', message });
      });
    return () => {
      cancelled = true;
    };
  }, [t]);

  const filtered = useMemo(() => {
    if (state.status !== 'ok') return [];
    const q = filter.trim().toLowerCase();
    if (!q) return state.breaches;
    return state.breaches.filter((b) => {
      const hay = [b.name, b.title, b.domain].filter(Boolean).join(' ').toLowerCase();
      return hay.includes(q);
    });
  }, [filter, state]);

  return (
    <section className="mx-auto max-w-5xl px-4 py-12">
      <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">{t('breaches.title')}</h1>
      <p className="mt-3 text-slate-600">{t('breaches.subtitle')}</p>

      <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <input
          type="search"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder={t('breaches.search_placeholder')}
          className="w-full rounded border border-slate-300 px-4 py-2 text-base shadow-sm focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand sm:max-w-sm"
        />
        {state.status === 'ok' && (
          <p className="text-sm text-slate-500">
            {filtered.length === 1
              ? t('breaches.count_label_one')
              : t('breaches.count_label_many', { count: filtered.length })}
          </p>
        )}
      </div>

      <div className="mt-8" aria-live="polite">
        {state.status === 'loading' && <p className="text-slate-500">{t('common.loading')}</p>}
        {state.status === 'error' && (
          <div className="rounded border border-red-300 bg-red-50 p-4 text-red-800">
            {state.message}
          </div>
        )}
        {state.status === 'ok' && filtered.length === 0 && (
          <p className="text-slate-500">{t('breaches.empty')}</p>
        )}
        {state.status === 'ok' && filtered.length > 0 && (
          <div className="grid gap-4 sm:grid-cols-2">
            {filtered.map((b) => (
              <BreachCard key={b.name} breach={b} href />
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
