import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { checkPassword } from '../lib/passwords';

export function PasswordsPage() {
  const { t } = useTranslation();
  const [password, setPassword] = useState('');
  const [state, setState] = useState<
    | { status: 'idle' }
    | { status: 'loading' }
    | { status: 'safe' }
    | { status: 'pwned'; count: number }
    | { status: 'error'; message: string }
  >({ status: 'idle' });

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!password) return;
    setState({ status: 'loading' });
    try {
      const result = await checkPassword(password);
      setState(
        result.count === 0
          ? { status: 'safe' }
          : { status: 'pwned', count: result.count },
      );
    } catch (err) {
      setState({ status: 'error', message: (err as Error).message });
    } finally {
      setPassword('');
    }
  }

  return (
    <section className="mx-auto max-w-2xl px-4 py-16">
      <h1 className="text-3xl font-bold tracking-tight">{t('passwords.title')}</h1>
      <p className="mt-3 text-slate-600">{t('passwords.subtitle')}</p>
      <p className="mt-2 text-sm text-slate-500">{t('passwords.privacy_note')}</p>

      <form onSubmit={onSubmit} className="mt-6 flex flex-col gap-3 sm:flex-row">
        <input
          type="password"
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder={t('passwords.placeholder')}
          className="flex-1 rounded border border-slate-300 px-4 py-3 text-base shadow-sm focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
        />
        <button
          type="submit"
          disabled={state.status === 'loading'}
          className="rounded bg-brand px-6 py-3 font-semibold text-white shadow-sm hover:bg-brand-dark disabled:opacity-50"
        >
          {state.status === 'loading' ? t('home.checking') : t('passwords.cta')}
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
            {t('passwords.result.pwned', { count: state.count })}
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
