import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router';

import { ApiError, confirmNotification } from '../lib/api';

type State =
  | { status: 'idle' }
  | { status: 'submitting' }
  | { status: 'success'; message: string }
  | { status: 'error'; message: string };

export function ConfirmPage() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const token = params.get('token') ?? '';
  const [state, setState] = useState<State>({ status: 'idle' });

  useEffect(() => {
    let cancelled = false;
    if (!token) {
      setState({ status: 'error', message: t('confirm.missing_token') });
      return;
    }
    setState({ status: 'submitting' });
    confirmNotification(token)
      .then((res) => {
        if (cancelled) return;
        setState({ status: 'success', message: res.message });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        let message = t('confirm.error');
        if (err instanceof ApiError) message = err.problem?.detail ?? message;
        setState({ status: 'error', message });
      });
    return () => {
      cancelled = true;
    };
  }, [token, t]);

  return (
    <section className="mx-auto max-w-2xl px-4 py-12 sm:py-16">
      <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">
        {t('confirm.title')}
      </h1>
      <p className="mt-3 text-slate-600">{t('confirm.subtitle')}</p>

      <div className="mt-6" aria-live="polite">
        {state.status === 'submitting' && (
          <div className="rounded border border-slate-200 bg-slate-50 p-4 text-slate-700">
            {t('confirm.verifying')}
          </div>
        )}
        {state.status === 'success' && (
          <div className="rounded border border-emerald-300 bg-emerald-50 p-4 text-emerald-800">
            {state.message}
          </div>
        )}
        {state.status === 'error' && (
          <div className="rounded border border-red-300 bg-red-50 p-4 text-red-800">
            {state.message}
          </div>
        )}
      </div>
    </section>
  );
}
