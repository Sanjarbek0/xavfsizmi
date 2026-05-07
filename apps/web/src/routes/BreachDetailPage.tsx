import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useParams } from 'react-router';
import type { BreachSummary } from '@xavfsizmi/shared-types';

import { ApiError, getBreach } from '../lib/api';
import { BreachCard } from '../components/BreachCard';

type State =
  | { status: 'loading' }
  | { status: 'ok'; breach: BreachSummary }
  | { status: 'not_found' }
  | { status: 'error'; message: string };

export function BreachDetailPage() {
  const { t } = useTranslation();
  const { locale = 'uz', name = '' } = useParams();
  const [state, setState] = useState<State>({ status: 'loading' });

  useEffect(() => {
    let cancelled = false;
    setState({ status: 'loading' });
    getBreach(name)
      .then((breach) => !cancelled && setState({ status: 'ok', breach }))
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) {
          setState({ status: 'not_found' });
          return;
        }
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
  }, [name, t]);

  return (
    <section className="mx-auto max-w-3xl px-4 py-12">
      <Link
        to={`/${locale}/breaches`}
        className="inline-block text-sm text-brand hover:underline"
      >
        ← {t('breach.back_to_list')}
      </Link>

      <div className="mt-6" aria-live="polite">
        {state.status === 'loading' && <p className="text-slate-500">{t('common.loading')}</p>}
        {state.status === 'error' && (
          <div className="rounded border border-red-300 bg-red-50 p-4 text-red-800">
            {state.message}
          </div>
        )}
        {state.status === 'not_found' && (
          <div className="rounded border border-slate-200 bg-slate-50 p-6">
            <h1 className="text-xl font-semibold text-slate-900">{t('breach.not_found_title')}</h1>
            <p className="mt-2 text-slate-600">{t('breach.not_found_body')}</p>
          </div>
        )}
        {state.status === 'ok' && (
          <div className="space-y-6">
            <BreachCard breach={state.breach} />
            <article className="rounded-lg border border-slate-200 bg-white p-6">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
                {t('breach.description_label')}
              </h2>
              {state.breach.description ? (
                <div
                  className="prose prose-sm mt-2 max-w-none text-slate-800"
                  dangerouslySetInnerHTML={{ __html: state.breach.description }}
                />
              ) : (
                <p className="mt-2 text-slate-500">{t('breach.no_description')}</p>
              )}
            </article>
          </div>
        )}
      </div>
    </section>
  );
}
