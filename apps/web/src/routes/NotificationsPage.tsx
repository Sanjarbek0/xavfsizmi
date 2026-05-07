import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router';

import { ApiError, subscribeNotifications } from '../lib/api';

type State =
  | { status: 'idle' }
  | { status: 'submitting' }
  | { status: 'success' }
  | { status: 'error'; message: string };

export function NotificationsPage() {
  const { t } = useTranslation();
  const { locale = 'uz' } = useParams();
  const [email, setEmail] = useState('');
  const [state, setState] = useState<State>({ status: 'idle' });

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const value = email.trim();
    if (!value) return;
    setState({ status: 'submitting' });
    try {
      await subscribeNotifications(value, locale);
      setState({ status: 'success' });
      setEmail('');
    } catch (err) {
      let message = t('notifications.error');
      if (err instanceof ApiError && err.status === 429) message = t('errors.rate_limited');
      else if (err instanceof TypeError) message = t('errors.network');
      setState({ status: 'error', message });
    }
  }

  return (
    <section className="mx-auto max-w-2xl px-4 py-12 sm:py-16">
      <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">
        {t('notifications.title')}
      </h1>
      <p className="mt-3 text-slate-600">{t('notifications.subtitle')}</p>

      <form onSubmit={onSubmit} className="mt-6 flex flex-col gap-3 sm:flex-row">
        <label className="sr-only" htmlFor="notification-email">
          {t('notifications.email_placeholder')}
        </label>
        <input
          id="notification-email"
          type="email"
          required
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder={t('notifications.email_placeholder')}
          className="flex-1 rounded border border-slate-300 px-4 py-3 text-base shadow-sm focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
        />
        <button
          type="submit"
          disabled={state.status === 'submitting'}
          className="rounded bg-brand px-6 py-3 font-semibold text-white shadow-sm hover:bg-brand-dark disabled:opacity-60"
        >
          {state.status === 'submitting' ? t('notifications.submitting') : t('notifications.cta')}
        </button>
      </form>

      <div className="mt-6" aria-live="polite">
        {state.status === 'success' && (
          <div className="rounded border border-emerald-300 bg-emerald-50 p-4 text-emerald-800">
            {t('notifications.success')}
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
