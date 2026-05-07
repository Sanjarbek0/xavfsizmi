import { useState } from 'react';
import type { FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router';

import { ApiError, requestMagicLink } from '../lib/api';

type Status = 'idle' | 'submitting' | 'success' | 'error';

export function SignInPage() {
  const { t } = useTranslation();
  const { locale = 'uz' } = useParams();
  const [email, setEmail] = useState('');
  const [status, setStatus] = useState<Status>('idle');
  const [error, setError] = useState<string | null>(null);
  const [serverMessage, setServerMessage] = useState<string | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setStatus('submitting');
    setError(null);
    try {
      const res = await requestMagicLink(email.trim(), locale, null, `/${locale}/account`);
      setServerMessage(res.message);
      setStatus('success');
    } catch (err) {
      const message =
        err instanceof ApiError ? err.problem?.detail ?? err.message : t('auth.request_error');
      setError(message);
      setStatus('error');
    }
  }

  return (
    <div className="mx-auto max-w-lg space-y-6 px-4 py-12">
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight">{t('auth.sign_in_title')}</h1>
        <p className="text-sm text-slate-600">{t('auth.sign_in_subtitle')}</p>
      </header>

      <form className="space-y-4" onSubmit={onSubmit}>
        <input
          type="email"
          required
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder={t('auth.email_placeholder')}
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20"
        />
        <button
          type="submit"
          disabled={status === 'submitting'}
          className="w-full rounded-md bg-brand px-4 py-2 text-sm font-medium text-white hover:bg-brand-dark disabled:opacity-50"
        >
          {status === 'submitting' ? t('auth.requesting') : t('auth.request_cta')}
        </button>
      </form>

      {status === 'success' ? (
        <div className="rounded-md border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
          {serverMessage ?? t('auth.request_success')}
        </div>
      ) : null}
      {status === 'error' && error ? (
        <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-900">
          {error}
        </div>
      ) : null}
    </div>
  );
}
