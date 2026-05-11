import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Navigate, useParams } from 'react-router';

import {
  ApiError,
  fetchSubscription,
  openBillingPortal,
  startCheckout,
} from '../lib/api';
import type { SubscriptionStatus } from '../lib/api';
import { useAuth } from '../lib/auth-context';

type CheckoutTier = 'pro' | 'high_rpm';

export function BillingPage() {
  const { t } = useTranslation();
  const { locale = 'uz' } = useParams();
  const { user, loading } = useAuth();
  const [subscription, setSubscription] = useState<SubscriptionStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    fetchSubscription()
      .then(setSubscription)
      .catch((err: unknown) => {
        if (err instanceof ApiError) setError(err.message);
      });
  }, [user]);

  if (loading) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-12 text-sm text-slate-600">
        {t('common.loading')}
      </div>
    );
  }
  if (!user) {
    return <Navigate to={`/${locale}/sign-in`} replace />;
  }

  async function onUpgrade(tier: CheckoutTier) {
    setBusy(true);
    setError(null);
    try {
      const res = await startCheckout({
        tier,
        successPath: `/${locale}/account/billing`,
        cancelPath: `/${locale}/account/billing`,
      });
      window.location.href = res.checkout_url;
    } catch (err) {
      setError(err instanceof ApiError ? (err.problem?.detail ?? err.message) : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onPortal() {
    setBusy(true);
    setError(null);
    try {
      const res = await openBillingPortal();
      window.location.href = res.portal_url;
    } catch (err) {
      setError(err instanceof ApiError ? (err.problem?.detail ?? err.message) : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6 px-4 py-10">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">{t('billing.title')}</h1>
        <p className="text-sm text-slate-600">{t('billing.subtitle')}</p>
      </header>

      <section className="rounded-md border border-slate-200 bg-white p-4">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
          {t('billing.current_plan')}
        </h2>
        {subscription ? (
          <dl className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
            <Stat label={t('billing.tier_label')} value={subscription.tier} />
            <Stat label={t('billing.status_label')} value={subscription.status} />
            <Stat
              label={t('billing.renews_label')}
              value={
                subscription.current_period_end
                  ? new Date(subscription.current_period_end).toLocaleDateString()
                  : t('billing.no_renewal')
              }
            />
          </dl>
        ) : (
          <p className="mt-2 text-sm text-slate-500">{t('common.loading')}</p>
        )}
      </section>

      <section className="rounded-md border border-slate-200 bg-white p-4">
        <h2 className="text-base font-semibold">{t('billing.upgrade_title')}</h2>
        <p className="mt-1 text-sm text-slate-600">{t('billing.upgrade_subtitle')}</p>
        <div className="mt-4 flex flex-col gap-2 sm:flex-row">
          <button
            disabled={busy}
            onClick={() => void onUpgrade('pro')}
            className="rounded bg-brand px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-brand-dark disabled:opacity-60"
          >
            {t('billing.upgrade_pro')}
          </button>
          <button
            disabled={busy}
            onClick={() => void onUpgrade('high_rpm')}
            className="rounded bg-slate-900 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-slate-700 disabled:opacity-60"
          >
            {t('billing.upgrade_high_rpm')}
          </button>
        </div>
      </section>

      {subscription?.has_customer ? (
        <section className="rounded-md border border-slate-200 bg-white p-4">
          <h2 className="text-base font-semibold">{t('billing.portal_title')}</h2>
          <p className="mt-1 text-sm text-slate-600">{t('billing.portal_subtitle')}</p>
          <button
            disabled={busy}
            onClick={() => void onPortal()}
            className="mt-3 inline-flex items-center rounded border border-slate-300 px-3 py-2 text-sm text-slate-700 hover:bg-slate-100 disabled:opacity-60"
          >
            {t('billing.open_portal')}
          </button>
        </section>
      ) : null}

      {error ? (
        <div className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800">{error}</div>
      ) : null}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-1 text-sm font-medium text-slate-900">{value}</div>
    </div>
  );
}
