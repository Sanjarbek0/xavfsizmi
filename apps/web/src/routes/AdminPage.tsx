import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Navigate, useParams } from 'react-router';

import {
  ApiError,
  fetchAdminAudit,
  fetchAdminBreaches,
  fetchAdminMetrics,
  fetchAdminUsers,
  setUserBlocked,
  upsertAdminBreach,
} from '../lib/api';
import type {
  AdminAuditRow,
  AdminBreachRow,
  AdminMetrics,
  AdminUserRow,
} from '../lib/api';
import { useAuth } from '../lib/auth-context';

type Tab = 'metrics' | 'users' | 'audit' | 'breaches';

export function AdminPage() {
  const { t } = useTranslation();
  const { locale = 'uz' } = useParams();
  const { user, loading } = useAuth();
  const [tab, setTab] = useState<Tab>('metrics');

  if (loading) {
    return (
      <div className="mx-auto max-w-5xl px-4 py-12 text-sm text-slate-600">
        {t('common.loading')}
      </div>
    );
  }
  if (!user) {
    return <Navigate to={`/${locale}/sign-in`} replace />;
  }
  if (!user.is_admin) {
    return (
      <div className="mx-auto max-w-3xl space-y-3 px-4 py-12">
        <h1 className="text-2xl font-semibold">{t('admin.forbidden_title')}</h1>
        <p className="text-sm text-slate-600">{t('admin.forbidden_detail')}</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6 px-4 py-10">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">{t('admin.title')}</h1>
        <p className="text-sm text-slate-600">{t('admin.subtitle')}</p>
      </header>

      <nav className="flex flex-wrap gap-2 border-b border-slate-200">
        {(['metrics', 'users', 'audit', 'breaches'] as const).map((key) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium ${
              tab === key
                ? 'border-brand text-brand'
                : 'border-transparent text-slate-600 hover:text-slate-900'
            }`}
          >
            {t(`admin.tabs.${key}`)}
          </button>
        ))}
      </nav>

      {tab === 'metrics' ? <MetricsPanel /> : null}
      {tab === 'users' ? <UsersPanel /> : null}
      {tab === 'audit' ? <AuditPanel /> : null}
      {tab === 'breaches' ? <BreachesPanel /> : null}
    </div>
  );
}

function MetricsPanel() {
  const { t } = useTranslation();
  const [metrics, setMetrics] = useState<AdminMetrics | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchAdminMetrics()
      .then(setMetrics)
      .catch((err: unknown) => setError(err instanceof ApiError ? err.message : String(err)));
  }, []);

  if (error) {
    return <ErrorBox message={error} />;
  }
  if (!metrics) {
    return <p className="text-sm text-slate-500">{t('common.loading')}</p>;
  }

  const rows: { label: string; value: number }[] = [
    { label: t('admin.metrics.users'), value: metrics.user_count },
    { label: t('admin.metrics.api_keys'), value: metrics.api_key_count },
    { label: t('admin.metrics.domains'), value: metrics.domain_count },
    { label: t('admin.metrics.subscribers'), value: metrics.notification_subscriber_count },
    { label: t('admin.metrics.cached_breaches'), value: metrics.cached_breach_count },
  ];

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      {rows.map((row) => (
        <div key={row.label} className="rounded border border-slate-200 bg-white p-4">
          <div className="text-xs uppercase tracking-wide text-slate-500">{row.label}</div>
          <div className="mt-1 text-2xl font-semibold text-slate-900">{row.value}</div>
        </div>
      ))}
    </div>
  );
}

function UsersPanel() {
  const { t } = useTranslation();
  const [users, setUsers] = useState<AdminUserRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    try {
      const list = await fetchAdminUsers();
      setUsers(list);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function toggle(row: AdminUserRow) {
    try {
      await setUserBlocked(row.id, !row.is_blocked);
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    }
  }

  return (
    <div className="space-y-3">
      {error ? <ErrorBox message={error} /> : null}
      <div className="overflow-x-auto rounded border border-slate-200">
        <table className="min-w-full text-sm">
          <thead className="bg-slate-50 text-left">
            <tr>
              <th className="px-3 py-2">{t('admin.users.email')}</th>
              <th className="px-3 py-2">{t('admin.users.role')}</th>
              <th className="px-3 py-2">{t('admin.users.status')}</th>
              <th className="px-3 py-2">{t('admin.users.created')}</th>
              <th className="px-3 py-2 text-right">{t('admin.users.actions')}</th>
            </tr>
          </thead>
          <tbody>
            {users.map((row) => (
              <tr key={row.id} className="border-t border-slate-100">
                <td className="px-3 py-2 font-medium text-slate-800">{row.email}</td>
                <td className="px-3 py-2 text-slate-600">
                  {row.is_admin ? t('admin.users.admin') : t('admin.users.user')}
                </td>
                <td className="px-3 py-2 text-slate-600">
                  {row.is_blocked ? t('admin.users.blocked') : t('admin.users.active')}
                </td>
                <td className="px-3 py-2 text-slate-500">
                  {new Date(row.created_at).toLocaleDateString()}
                </td>
                <td className="px-3 py-2 text-right">
                  <button
                    onClick={() => void toggle(row)}
                    className="rounded border border-slate-300 px-2 py-1 text-xs text-slate-700 hover:bg-slate-100"
                  >
                    {row.is_blocked ? t('admin.users.unblock') : t('admin.users.block')}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function AuditPanel() {
  const { t } = useTranslation();
  const [rows, setRows] = useState<AdminAuditRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchAdminAudit()
      .then(setRows)
      .catch((err: unknown) => setError(err instanceof ApiError ? err.message : String(err)));
  }, []);

  if (error) return <ErrorBox message={error} />;

  return (
    <div className="overflow-x-auto rounded border border-slate-200">
      <table className="min-w-full text-sm">
        <thead className="bg-slate-50 text-left">
          <tr>
            <th className="px-3 py-2">{t('admin.audit.when')}</th>
            <th className="px-3 py-2">{t('admin.audit.action')}</th>
            <th className="px-3 py-2">{t('admin.audit.target')}</th>
            <th className="px-3 py-2">{t('admin.audit.actor')}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id} className="border-t border-slate-100">
              <td className="px-3 py-2 text-slate-500">
                {new Date(row.created_at).toLocaleString()}
              </td>
              <td className="px-3 py-2 font-mono text-xs text-slate-700">{row.action}</td>
              <td className="px-3 py-2 text-slate-600">
                {row.target_type ?? '—'}{row.target_id ? ` · ${row.target_id}` : ''}
              </td>
              <td className="px-3 py-2 text-slate-600">{row.actor_ip ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function BreachesPanel() {
  const { t } = useTranslation();
  const [breaches, setBreaches] = useState<AdminBreachRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState<AdminBreachRow>({
    name: '',
    title: '',
    domain: '',
    breach_date: '',
    pwn_count: 0,
    is_verified: true,
    is_sensitive: false,
    description: '',
    data_classes: null,
  });

  async function refresh() {
    try {
      const list = await fetchAdminBreaches();
      setBreaches(list);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      await upsertAdminBreach(draft);
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    }
  }

  return (
    <div className="space-y-4">
      {error ? <ErrorBox message={error} /> : null}
      <form onSubmit={onSubmit} className="grid grid-cols-1 gap-2 rounded border border-slate-200 bg-white p-4 sm:grid-cols-2">
        <input
          required
          value={draft.name}
          onChange={(e) => setDraft({ ...draft, name: e.target.value })}
          placeholder={t('admin.breaches.name_placeholder')}
          className="rounded border border-slate-300 px-3 py-2 text-sm"
        />
        <input
          value={draft.title ?? ''}
          onChange={(e) => setDraft({ ...draft, title: e.target.value })}
          placeholder={t('admin.breaches.title_placeholder')}
          className="rounded border border-slate-300 px-3 py-2 text-sm"
        />
        <input
          value={draft.domain ?? ''}
          onChange={(e) => setDraft({ ...draft, domain: e.target.value })}
          placeholder={t('admin.breaches.domain_placeholder')}
          className="rounded border border-slate-300 px-3 py-2 text-sm"
        />
        <input
          value={draft.breach_date ?? ''}
          onChange={(e) => setDraft({ ...draft, breach_date: e.target.value })}
          placeholder={t('admin.breaches.date_placeholder')}
          className="rounded border border-slate-300 px-3 py-2 text-sm"
        />
        <textarea
          value={draft.description ?? ''}
          onChange={(e) => setDraft({ ...draft, description: e.target.value })}
          placeholder={t('admin.breaches.description_placeholder')}
          className="col-span-full rounded border border-slate-300 px-3 py-2 text-sm"
        />
        <button type="submit" className="col-span-full rounded bg-brand px-3 py-2 text-sm font-medium text-white hover:bg-brand-dark">
          {t('admin.breaches.save')}
        </button>
      </form>

      <div className="overflow-x-auto rounded border border-slate-200">
        <table className="min-w-full text-sm">
          <thead className="bg-slate-50 text-left">
            <tr>
              <th className="px-3 py-2">{t('admin.breaches.col_name')}</th>
              <th className="px-3 py-2">{t('admin.breaches.col_title')}</th>
              <th className="px-3 py-2">{t('admin.breaches.col_domain')}</th>
              <th className="px-3 py-2">{t('admin.breaches.col_date')}</th>
            </tr>
          </thead>
          <tbody>
            {breaches.map((row) => (
              <tr key={row.name} className="border-t border-slate-100">
                <td className="px-3 py-2 font-medium text-slate-800">{row.name}</td>
                <td className="px-3 py-2 text-slate-600">{row.title ?? '—'}</td>
                <td className="px-3 py-2 text-slate-600">{row.domain ?? '—'}</td>
                <td className="px-3 py-2 text-slate-600">{row.breach_date ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ErrorBox({ message }: { message: string }) {
  return (
    <div className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800">{message}</div>
  );
}
