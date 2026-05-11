import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Navigate, useParams, useSearchParams } from 'react-router';

import {
  ApiError,
  fetchSubscription,
  openBillingPortal,
  startCheckout,
} from '../lib/api';
import type { ApiKeyTier, SubscriptionStatus, TierLimit } from '../lib/api';
import { useAuth } from '../lib/auth-context';

type CheckoutTier = 'pro' | 'high_rpm';

export function BillingPage() {
  const { t } = useTranslation();
  const { locale = 'uz' } = useParams();
  const { user, loading } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const [subscription, setSubscription] = useState<SubscriptionStatus | null>(null);
  const [busy, setBusy] = useState<CheckoutTier | 'portal' | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    return fetchSubscription()
      .then(setSubscription)
      .catch((err: unknown) => {
        if (err instanceof ApiError) setError(err.message);
      });
  }, []);

  useEffect(() => {
    if (!user) return;
    void refresh();
  }, [user, refresh]);

  const checkoutResult = searchParams.get('checkout');

  function dismissCheckoutToast() {
    const next = new URLSearchParams(searchParams);
    next.delete('checkout');
    setSearchParams(next, { replace: true });
  }

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

  async function onSelect(tier: CheckoutTier) {
    setBusy(tier);
    setError(null);
    try {
      const res = await startCheckout({
        tier,
        successPath: `/${locale}/account/billing?checkout=success`,
        cancelPath: `/${locale}/account/billing?checkout=cancel`,
      });
      window.location.href = res.checkout_url;
    } catch (err) {
      setError(err instanceof ApiError ? (err.problem?.detail ?? err.message) : String(err));
    } finally {
      setBusy(null);
    }
  }

  async function onPortal() {
    setBusy('portal');
    setError(null);
    try {
      const res = await openBillingPortal();
      window.location.href = res.portal_url;
    } catch (err) {
      setError(err instanceof ApiError ? (err.problem?.detail ?? err.message) : String(err));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6 px-4 py-10">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">{t('billing.title')}</h1>
        <p className="text-sm text-slate-600">{t('billing.subtitle')}</p>
      </header>

      {checkoutResult === 'success' ? (
        <Toast
          variant="success"
          title={t('billing.checkout_success_title')}
          detail={t('billing.checkout_success_detail')}
          onDismiss={dismissCheckoutToast}
        />
      ) : null}
      {checkoutResult === 'cancel' ? (
        <Toast
          variant="info"
          title={t('billing.checkout_cancel_title')}
          detail={t('billing.checkout_cancel_detail')}
          onDismiss={dismissCheckoutToast}
        />
      ) : null}

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

      <section className="space-y-3">
        <h2 className="text-base font-semibold">{t('billing.upgrade_title')}</h2>
        <p className="text-sm text-slate-600">{t('billing.upgrade_subtitle')}</p>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {(['free', 'pro', 'high_rpm'] as const).map((tier) => {
            const props = {
              tier,
              limit: subscription?.available_tiers.find((l) => l.tier === tier),
              isCurrent: subscription?.tier === tier,
              busy: busy === tier,
              ...(tier !== 'free'
                ? { onSelect: () => void onSelect(tier as CheckoutTier) }
                : {}),
            } as const;
            return <PlanCard key={tier} {...props} />;
          })}
        </div>
      </section>

      {subscription?.has_customer ? (
        <section className="rounded-md border border-slate-200 bg-white p-4">
          <h2 className="text-base font-semibold">{t('billing.portal_title')}</h2>
          <p className="mt-1 text-sm text-slate-600">{t('billing.portal_subtitle')}</p>
          <button
            disabled={busy === 'portal'}
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

function PlanCard({
  tier,
  limit,
  isCurrent,
  busy,
  onSelect,
}: {
  tier: ApiKeyTier;
  limit: TierLimit | undefined;
  isCurrent: boolean;
  busy: boolean;
  onSelect?: () => void;
}) {
  const { t } = useTranslation();
  return (
    <article
      data-testid={`plan-${tier}`}
      className={`flex flex-col justify-between rounded-md border bg-white p-4 ${
        isCurrent ? 'border-brand ring-1 ring-brand' : 'border-slate-200'
      }`}
    >
      <div>
        <div className="flex items-start justify-between">
          <h3 className="text-base font-semibold">{t(`billing.plans.${tier}_name`)}</h3>
          {isCurrent ? (
            <span className="rounded-full bg-brand/10 px-2 py-0.5 text-xs font-medium text-brand">
              {t('billing.current_tier_badge')}
            </span>
          ) : null}
        </div>
        <p className="mt-2 text-sm text-slate-600">{t(`billing.plans.${tier}_detail`)}</p>
        {limit ? (
          <p className="mt-3 text-sm font-medium text-slate-900">
            {limit.requests_per_minute}
            {t('api_keys.usage.rpm_suffix')}
          </p>
        ) : null}
      </div>
      {onSelect ? (
        <button
          type="button"
          onClick={onSelect}
          disabled={busy || isCurrent}
          className="mt-4 inline-flex items-center justify-center rounded bg-brand px-3 py-2 text-sm font-medium text-white hover:bg-brand-dark disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isCurrent
            ? t('billing.current_tier_badge')
            : busy
              ? t('common.loading')
              : t('billing.select_cta')}
        </button>
      ) : (
        <div className="mt-4 inline-flex items-center justify-center rounded border border-slate-200 px-3 py-2 text-sm text-slate-500">
          {isCurrent ? t('billing.current_tier_badge') : t('billing.plans.free_name')}
        </div>
      )}
    </article>
  );
}

function Toast({
  variant,
  title,
  detail,
  onDismiss,
}: {
  variant: 'success' | 'info';
  title: string;
  detail: string;
  onDismiss: () => void;
}) {
  const colour =
    variant === 'success'
      ? 'border-emerald-300 bg-emerald-50 text-emerald-900'
      : 'border-amber-300 bg-amber-50 text-amber-900';
  return (
    <div
      role="status"
      className={`flex items-start justify-between rounded-md border px-4 py-3 ${colour}`}
    >
      <div>
        <div className="text-sm font-semibold">{title}</div>
        <div className="mt-1 text-sm">{detail}</div>
      </div>
      <button
        type="button"
        onClick={onDismiss}
        className="ml-3 text-xs font-medium underline"
      >
        ×
      </button>
    </div>
  );
}
