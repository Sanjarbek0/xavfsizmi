import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router';

import { ApiError, verifyMagicLink } from '../lib/api';
import { useAuth } from '../lib/auth-context';

type Status = 'verifying' | 'success' | 'error';

export function VerifyMagicLinkPage() {
  const { t } = useTranslation();
  const { locale = 'uz' } = useParams();
  const [search] = useSearchParams();
  const navigate = useNavigate();
  const { setUser } = useAuth();
  const [status, setStatus] = useState<Status>('verifying');
  const [error, setError] = useState<string | null>(null);
  const ran = useRef(false);

  const token = search.get('token') ?? '';
  const next = search.get('next') ?? `/${locale}/account`;

  useEffect(() => {
    if (ran.current) return;
    ran.current = true;
    if (!token) {
      setError(t('auth.verify_failed_body'));
      setStatus('error');
      return;
    }
    void (async () => {
      try {
        const me = await verifyMagicLink(token);
        setUser(me);
        setStatus('success');
        navigate(next, { replace: true });
      } catch (err) {
        const detail = err instanceof ApiError ? err.problem?.detail ?? err.message : null;
        setError(detail ?? t('auth.verify_failed_body'));
        setStatus('error');
      }
    })();
  }, [token, t, next, navigate, setUser]);

  if (status === 'verifying') {
    return (
      <div className="mx-auto max-w-lg space-y-3 px-4 py-12 text-center">
        <h1 className="text-2xl font-semibold">{t('auth.verifying_title')}</h1>
        <p className="text-sm text-slate-600">{t('auth.verifying_subtitle')}</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-lg space-y-4 px-4 py-12">
      <h1 className="text-2xl font-semibold text-red-700">{t('auth.verify_failed_title')}</h1>
      <p className="text-sm text-slate-600">{error ?? t('auth.verify_failed_body')}</p>
      <Link
        to={`/${locale}/sign-in`}
        className="inline-block rounded-md bg-brand px-4 py-2 text-sm font-medium text-white hover:bg-brand-dark"
      >
        {t('auth.back_to_sign_in')}
      </Link>
    </div>
  );
}
