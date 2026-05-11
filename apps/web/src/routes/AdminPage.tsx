import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Navigate, useParams } from 'react-router';

import {
  ApiError,
  dispatchAdminNotifications,
  fetchAdminAudit,
  fetchAdminBreachStats,
  fetchAdminBreaches,
  fetchAdminMetrics,
  fetchAdminUserStats,
  fetchAdminUsers,
  setUserBlocked,
  uploadAdminBreachesCsv,
  upsertAdminBreach,
} from '../lib/api';
import type {
  AdminAuditRow,
  AdminBreachRow,
  AdminBreachStats,
  AdminCsvImportResponse,
  AdminDailyPoint,
  AdminDispatchResponse,
  AdminMetrics,
  AdminUserRow,
  AdminUserStats,
} from '../lib/api';
import { useAuth } from '../lib/auth-context';

type Tab = 'metrics' | 'users' | 'audit' | 'breaches' | 'stats' | 'notify';

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
        {(['metrics', 'stats', 'users', 'audit', 'breaches', 'notify'] as const).map((key) => (
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
      {tab === 'stats' ? <StatsPanel /> : null}
      {tab === 'users' ? <UsersPanel /> : null}
      {tab === 'audit' ? <AuditPanel /> : null}
      {tab === 'breaches' ? <BreachesPanel /> : null}
      {tab === 'notify' ? <NotifyPanel /> : null}
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
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [csvDryRun, setCsvDryRun] = useState(false);
  const [csvResult, setCsvResult] = useState<AdminCsvImportResponse | null>(null);
  const [csvBusy, setCsvBusy] = useState(false);

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

  async function onCsvSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setCsvResult(null);
    if (!csvFile) {
      setError(t('admin.breaches.csv_no_file'));
      return;
    }
    setCsvBusy(true);
    try {
      const result = await uploadAdminBreachesCsv(csvFile, { dryRun: csvDryRun });
      setCsvResult(result);
      if (!csvDryRun) {
        await refresh();
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setCsvBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      {error ? <ErrorBox message={error} /> : null}

      <form
        onSubmit={onCsvSubmit}
        className="space-y-2 rounded border border-slate-200 bg-white p-4"
      >
        <h2 className="text-sm font-semibold text-slate-800">
          {t('admin.breaches.csv_heading')}
        </h2>
        <p className="text-xs text-slate-500">{t('admin.breaches.csv_hint')}</p>
        <div className="flex flex-wrap items-center gap-3">
          <label className="text-sm text-slate-700">
            <span className="sr-only">{t('admin.breaches.csv_choose')}</span>
            <input
              type="file"
              accept=".csv,text/csv"
              onChange={(e) => setCsvFile(e.target.files?.[0] ?? null)}
              className="block text-sm text-slate-700"
            />
          </label>
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={csvDryRun}
              onChange={(e) => setCsvDryRun(e.target.checked)}
            />
            {t('admin.breaches.csv_dry_run')}
          </label>
          <button
            type="submit"
            disabled={csvBusy}
            className="rounded bg-brand px-3 py-2 text-sm font-medium text-white hover:bg-brand-dark disabled:cursor-not-allowed disabled:opacity-60"
          >
            {t('admin.breaches.csv_upload')}
          </button>
        </div>
        {csvResult ? (
          <div className="space-y-1 rounded border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700">
            {csvResult.dry_run ? (
              <p className="font-medium text-slate-800">
                {t('admin.breaches.csv_result_dry_run')}
              </p>
            ) : null}
            <p>
              {t('admin.breaches.csv_result_inserted')}: {csvResult.inserted}
              {' · '}
              {t('admin.breaches.csv_result_updated')}: {csvResult.updated}
              {' · '}
              {t('admin.breaches.csv_result_skipped')}: {csvResult.skipped}
            </p>
            {csvResult.errors.length ? (
              <ul className="max-h-32 list-disc space-y-0.5 overflow-auto pl-5">
                {csvResult.errors.map((errRow) => (
                  <li key={`${errRow.line}-${errRow.message}`}>
                    line {errRow.line}: {errRow.message}
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}
      </form>

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

function StatsPanel() {
  const { t } = useTranslation();
  const [users, setUsers] = useState<AdminUserStats | null>(null);
  const [breaches, setBreaches] = useState<AdminBreachStats | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchAdminUserStats()
      .then(setUsers)
      .catch((err: unknown) =>
        setError(err instanceof ApiError ? err.message : String(err)),
      );
    fetchAdminBreachStats(10)
      .then(setBreaches)
      .catch((err: unknown) =>
        setError(err instanceof ApiError ? err.message : String(err)),
      );
  }, []);

  if (error) return <ErrorBox message={error} />;
  if (!users || !breaches) {
    return <p className="text-sm text-slate-500">{t('common.loading')}</p>;
  }

  const userTiles: { label: string; value: number }[] = [
    { label: t('admin.stats.total_users'), value: users.total_users },
    { label: t('admin.stats.blocked_users'), value: users.blocked_users },
    { label: t('admin.stats.admin_users'), value: users.admin_users },
    { label: t('admin.stats.active_subscribers'), value: users.active_subscribers },
    { label: t('admin.stats.pending_subscribers'), value: users.pending_subscribers },
  ];
  const breachTiles: { label: string; value: number }[] = [
    { label: t('admin.stats.total_breaches'), value: breaches.total_breaches },
    { label: t('admin.stats.sensitive_breaches'), value: breaches.sensitive_breaches },
    { label: t('admin.stats.verified_breaches'), value: breaches.verified_breaches },
    { label: t('admin.stats.total_pwn_count'), value: breaches.total_pwn_count },
  ];

  return (
    <div className="space-y-6">
      <section className="space-y-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-600">
          {t('admin.stats.heading_users')}
        </h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          {userTiles.map((row) => (
            <Tile key={row.label} label={row.label} value={row.value} />
          ))}
        </div>
        <BreakdownTable
          title={t('admin.stats.by_tier')}
          rows={Object.entries(users.by_tier)}
        />
        <BreakdownTable
          title={t('admin.stats.by_subscription_status')}
          rows={Object.entries(users.by_subscription_status)}
        />
        <ChartCard
          title={t('admin.stats.signups_chart')}
          points={users.signups_last_30_days}
        />
      </section>

      <section className="space-y-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-600">
          {t('admin.stats.heading_breaches')}
        </h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {breachTiles.map((row) => (
            <Tile key={row.label} label={row.label} value={row.value} />
          ))}
        </div>
        <div className="overflow-x-auto rounded border border-slate-200 bg-white">
          <div className="border-b border-slate-100 px-3 py-2 text-xs font-medium uppercase tracking-wide text-slate-500">
            {t('admin.stats.top_by_pwn_count')}
          </div>
          <table className="min-w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-3 py-2">{t('admin.breaches.col_name')}</th>
                <th className="px-3 py-2">{t('admin.breaches.col_title')}</th>
                <th className="px-3 py-2">{t('admin.stats.pwn_count')}</th>
                <th className="px-3 py-2">{t('admin.breaches.col_date')}</th>
              </tr>
            </thead>
            <tbody>
              {breaches.top_by_pwn_count.map((row) => (
                <tr key={row.name} className="border-t border-slate-100">
                  <td className="px-3 py-2 font-medium text-slate-800">{row.name}</td>
                  <td className="px-3 py-2 text-slate-600">{row.title ?? '—'}</td>
                  <td className="px-3 py-2 text-slate-600">
                    {row.pwn_count != null ? row.pwn_count.toLocaleString() : '—'}
                  </td>
                  <td className="px-3 py-2 text-slate-600">{row.breach_date ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <ChartCard
          title={t('admin.stats.breaches_chart')}
          points={breaches.breaches_added_last_30_days}
        />
      </section>
    </div>
  );
}

function Tile({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded border border-slate-200 bg-white p-4">
      <div className="text-xs uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-1 text-2xl font-semibold text-slate-900">
        {value.toLocaleString()}
      </div>
    </div>
  );
}

function BreakdownTable({
  title,
  rows,
}: {
  title: string;
  rows: [string, number][];
}) {
  if (!rows.length) return null;
  return (
    <div className="rounded border border-slate-200 bg-white">
      <div className="border-b border-slate-100 px-3 py-2 text-xs font-medium uppercase tracking-wide text-slate-500">
        {title}
      </div>
      <table className="min-w-full text-sm">
        <tbody>
          {rows.map(([key, value]) => (
            <tr key={key} className="border-t border-slate-100">
              <td className="px-3 py-2 font-mono text-xs text-slate-700">{key}</td>
              <td className="px-3 py-2 text-right text-slate-700">
                {value.toLocaleString()}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ChartCard({ title, points }: { title: string; points: AdminDailyPoint[] }) {
  return (
    <div className="rounded border border-slate-200 bg-white p-3">
      <div className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">
        {title}
      </div>
      <Sparkline points={points} />
    </div>
  );
}

function Sparkline({ points }: { points: AdminDailyPoint[] }) {
  const width = 480;
  const height = 80;
  if (points.length === 0) {
    return <div className="text-xs text-slate-400">—</div>;
  }
  const max = Math.max(1, ...points.map((p) => p.count));
  const barWidth = width / points.length;
  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      width="100%"
      height={height}
      role="img"
      preserveAspectRatio="none"
    >
      {points.map((p, i) => {
        const barHeight = (p.count / max) * (height - 4);
        return (
          <rect
            key={p.day}
            x={i * barWidth + 1}
            y={height - barHeight}
            width={Math.max(1, barWidth - 2)}
            height={barHeight}
            fill="#1d4ed8"
            opacity={0.85}
          >
            <title>{`${p.day}: ${p.count}`}</title>
          </rect>
        );
      })}
    </svg>
  );
}

function NotifyPanel() {
  const { t } = useTranslation();
  const [breaches, setBreaches] = useState<AdminBreachRow[]>([]);
  const [breachName, setBreachName] = useState('');
  const [limit, setLimit] = useState<string>('');
  const [dryRun, setDryRun] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AdminDispatchResponse | null>(null);

  useEffect(() => {
    fetchAdminBreaches()
      .then((list) => {
        setBreaches(list);
        const first = list[0];
        if (first && !breachName) {
          setBreachName(first.name);
        }
      })
      .catch((err: unknown) =>
        setError(err instanceof ApiError ? err.message : String(err)),
      );
    // We intentionally only run this on mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setResult(null);
    setBusy(true);
    try {
      const parsed = limit.trim() ? Math.max(1, Number.parseInt(limit, 10)) : null;
      const response = await dispatchAdminNotifications({
        breach_name: breachName,
        dry_run: dryRun,
        limit: Number.isFinite(parsed) ? parsed : null,
      });
      setResult(response);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      {error ? <ErrorBox message={error} /> : null}
      <header>
        <h2 className="text-sm font-semibold text-slate-800">{t('admin.notify.heading')}</h2>
        <p className="text-xs text-slate-500">{t('admin.notify.subtitle')}</p>
      </header>
      <form
        onSubmit={onSubmit}
        className="space-y-3 rounded border border-slate-200 bg-white p-4"
      >
        <label className="block text-sm text-slate-700">
          <span className="mb-1 block">{t('admin.notify.breach_label')}</span>
          <select
            value={breachName}
            onChange={(e) => setBreachName(e.target.value)}
            className="w-full rounded border border-slate-300 px-3 py-2 text-sm"
            required
          >
            {breaches.map((row) => (
              <option key={row.name} value={row.name}>
                {row.title ?? row.name}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-sm text-slate-700">
          <span className="mb-1 block">{t('admin.notify.limit_label')}</span>
          <input
            value={limit}
            onChange={(e) => setLimit(e.target.value)}
            type="number"
            min={1}
            placeholder="e.g. 25"
            className="w-32 rounded border border-slate-300 px-3 py-2 text-sm"
          />
        </label>
        <label className="flex items-center gap-2 text-sm text-slate-700">
          <input
            type="checkbox"
            checked={dryRun}
            onChange={(e) => setDryRun(e.target.checked)}
          />
          {t('admin.notify.dry_run')}
        </label>
        <button
          type="submit"
          disabled={busy || !breachName}
          className="rounded bg-brand px-3 py-2 text-sm font-medium text-white hover:bg-brand-dark disabled:cursor-not-allowed disabled:opacity-60"
        >
          {t('admin.notify.send')}
        </button>
      </form>

      {result ? (
        <div className="space-y-2 rounded border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700">
          <p>
            <strong>{result.breach_title || result.breach_name}</strong>
            {' · '}
            {t('admin.notify.subscribers_total')}: {result.total_subscribers}
          </p>
          <p>
            {t('admin.notify.sent')}: {result.sent}
            {' · '}
            {t('admin.notify.failed')}: {result.failed}
            {' · '}
            {t('admin.notify.skipped')}: {result.skipped}
          </p>
          {result.recipients.length ? (
            <div className="overflow-x-auto rounded border border-slate-200 bg-white">
              <table className="min-w-full text-xs">
                <tbody>
                  {result.recipients.slice(0, 25).map((row) => (
                    <tr key={row.email} className="border-t border-slate-100">
                      <td className="px-3 py-1.5 font-mono text-slate-700">{row.email}</td>
                      <td className="px-3 py-1.5 text-slate-600">
                        {row.sent
                          ? t('admin.notify.sent')
                          : row.error || t('admin.notify.skipped')}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-xs text-slate-500">{t('admin.notify.no_subscribers')}</p>
          )}
        </div>
      ) : null}
    </div>
  );
}
