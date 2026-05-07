import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { checkPassword } from '../lib/passwords';

type State =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'safe' }
  | { status: 'pwned'; count: number }
  | { status: 'error'; message: string };

function formatNumber(n: number, locale: string): string {
  try {
    return new Intl.NumberFormat(locale).format(n);
  } catch {
    return String(n);
  }
}

export function PasswordsPage() {
  const { t, i18n } = useTranslation();
  const [password, setPassword] = useState('');
  const [reveal, setReveal] = useState(false);
  const [state, setState] = useState<State>({ status: 'idle' });

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!password) return;
    setState({ status: 'loading' });
    try {
      const result = await checkPassword(password);
      setState(
        result.count === 0 ? { status: 'safe' } : { status: 'pwned', count: result.count },
      );
    } catch (err) {
      const message = err instanceof TypeError ? t('errors.network') : (err as Error).message;
      setState({ status: 'error', message });
    } finally {
      setPassword('');
    }
  }

  return (
    <section className="mx-auto max-w-2xl px-4 py-12 sm:py-16">
      <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">{t('passwords.title')}</h1>
      <p className="mt-3 text-slate-600">{t('passwords.subtitle')}</p>
      <p className="mt-2 text-sm text-slate-500">{t('passwords.privacy_note')}</p>

      <form onSubmit={onSubmit} className="mt-6 flex flex-col gap-3 sm:flex-row">
        <div className="relative flex-1">
          <label className="sr-only" htmlFor="password-input">
            {t('passwords.placeholder')}
          </label>
          <input
            id="password-input"
            type={reveal ? 'text' : 'password'}
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={t('passwords.placeholder')}
            className="w-full rounded border border-slate-300 px-4 py-3 pr-20 text-base shadow-sm focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
          />
          <button
            type="button"
            onClick={() => setReveal((r) => !r)}
            className="absolute inset-y-0 right-2 my-auto h-8 rounded px-2 text-xs font-medium text-slate-500 hover:bg-slate-100"
          >
            {reveal ? t('passwords.hide') : t('passwords.show')}
          </button>
        </div>
        <button
          type="submit"
          disabled={state.status === 'loading'}
          className="rounded bg-brand px-6 py-3 font-semibold text-white shadow-sm hover:bg-brand-dark disabled:opacity-60"
        >
          {state.status === 'loading' ? t('passwords.checking') : t('passwords.cta')}
        </button>
      </form>

      <div className="mt-8" aria-live="polite">
        {state.status === 'safe' && (
          <div className="rounded border border-emerald-300 bg-emerald-50 p-4 text-emerald-800">
            {t('passwords.result.safe')}
          </div>
        )}
        {state.status === 'pwned' && (
          <div className="rounded border border-red-300 bg-red-50 p-4 text-red-800">
            {state.count === 1
              ? t('passwords.result.pwned_one')
              : t('passwords.result.pwned_many', {
                  count: state.count,
                  formattedCount: formatNumber(state.count, i18n.language),
                })}
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
