import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Navigate, useParams } from 'react-router';

import {
  ApiError,
  createApiKey,
  deleteDomain,
  listApiKeys,
  listDomains,
  registerDomain,
  revokeApiKey,
  verifyDomain,
} from '../lib/api';
import type { ApiKeyRow, ApiKeyTier, DomainMethod, DomainRow } from '../lib/api';
import { useAuth } from '../lib/auth-context';

type Tab = 'overview' | 'api_keys' | 'domains';

export function AccountPage() {
  const { t } = useTranslation();
  const { locale = 'uz' } = useParams();
  const { user, loading, signOut } = useAuth();
  const [tab, setTab] = useState<Tab>('overview');

  if (loading) {
    return <div className="mx-auto max-w-4xl px-4 py-12 text-sm text-slate-600">{t('common.loading')}</div>;
  }
  if (!user) {
    return <Navigate to={`/${locale}/sign-in`} replace />;
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6 px-4 py-10">
      <header className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{t('account.title')}</h1>
          <p className="text-sm text-slate-600">{t('account.signed_in_as', { email: user.email })}</p>
        </div>
        <button
          onClick={() => void signOut()}
          className="inline-flex items-center justify-center rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100"
        >
          {t('auth.sign_out')}
        </button>
      </header>

      <nav className="flex gap-2 border-b border-slate-200">
        {(['overview', 'api_keys', 'domains'] as const).map((key) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium ${
              tab === key
                ? 'border-brand text-brand'
                : 'border-transparent text-slate-600 hover:text-slate-900'
            }`}
          >
            {t(`account.tabs.${key}`)}
          </button>
        ))}
      </nav>

      {tab === 'overview' ? <OverviewPanel /> : null}
      {tab === 'api_keys' ? <ApiKeysPanel /> : null}
      {tab === 'domains' ? <DomainsPanel /> : null}
    </div>
  );
}

function OverviewPanel() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const lastLogin = user?.last_login_at
    ? new Date(user.last_login_at).toLocaleString()
    : t('account.overview.never');
  return (
    <section className="space-y-4">
      <p className="text-sm text-slate-600">{t('account.overview.subtitle')}</p>
      <p className="text-sm text-slate-700">
        {t('account.overview.last_login', { when: lastLogin })}
      </p>
    </section>
  );
}

function ApiKeysPanel() {
  const { t } = useTranslation();
  const [keys, setKeys] = useState<ApiKeyRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [label, setLabel] = useState('');
  const [tier, setTier] = useState<ApiKeyTier>('free');
  const [creating, setCreating] = useState(false);
  const [plaintext, setPlaintext] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setLoading(true);
    try {
      const items = await listApiKeys();
      setKeys(items);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function onCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCreating(true);
    setError(null);
    try {
      const created = await createApiKey(label.trim() || 'API key', tier);
      setPlaintext(created.plaintext);
      setLabel('');
      setCopied(false);
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setCreating(false);
    }
  }

  async function onRevoke(id: string) {
    if (!confirm(t('api_keys.confirm_revoke'))) return;
    try {
      await revokeApiKey(id);
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    }
  }

  async function copyKey() {
    if (!plaintext) return;
    try {
      await navigator.clipboard.writeText(plaintext);
      setCopied(true);
    } catch {
      // ignore
    }
  }

  return (
    <section className="space-y-6">
      <header className="space-y-1">
        <h2 className="text-lg font-semibold">{t('api_keys.title')}</h2>
        <p className="text-sm text-slate-600">{t('api_keys.subtitle')}</p>
      </header>

      {plaintext ? (
        <div className="space-y-3 rounded-md border border-amber-300 bg-amber-50 p-4">
          <div className="font-semibold text-amber-900">{t('api_keys.show_once_title')}</div>
          <p className="text-sm text-amber-900">{t('api_keys.show_once_body')}</p>
          <code className="block break-all rounded bg-white px-3 py-2 font-mono text-xs">{plaintext}</code>
          <button
            type="button"
            onClick={() => void copyKey()}
            className="rounded-md bg-amber-700 px-3 py-1.5 text-xs font-medium text-white"
          >
            {copied ? t('api_keys.copied') : t('api_keys.copy')}
          </button>
        </div>
      ) : null}

      <form className="grid gap-3 sm:grid-cols-[2fr,1fr,auto]" onSubmit={onCreate}>
        <input
          type="text"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          placeholder={t('api_keys.label_placeholder')}
          className="rounded-md border border-slate-300 px-3 py-2 text-sm"
        />
        <select
          value={tier}
          onChange={(e) => setTier(e.target.value as ApiKeyTier)}
          className="rounded-md border border-slate-300 px-3 py-2 text-sm"
        >
          <option value="free">{t('api_keys.tier_free')}</option>
          <option value="pro">{t('api_keys.tier_pro')}</option>
          <option value="high_rpm">{t('api_keys.tier_high_rpm')}</option>
        </select>
        <button
          type="submit"
          disabled={creating}
          className="rounded-md bg-brand px-4 py-2 text-sm font-medium text-white hover:bg-brand-dark disabled:opacity-50"
        >
          {creating ? t('api_keys.creating') : t('api_keys.create_cta')}
        </button>
      </form>

      {error ? (
        <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900">{error}</div>
      ) : null}

      {loading ? (
        <p className="text-sm text-slate-600">{t('common.loading')}</p>
      ) : keys.length === 0 ? (
        <p className="rounded-md border border-dashed border-slate-300 px-4 py-6 text-center text-sm text-slate-600">
          {t('api_keys.empty')}
        </p>
      ) : (
        <div className="overflow-x-auto rounded-md border border-slate-200">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-600">
              <tr>
                <th className="px-3 py-2">{t('api_keys.table_label')}</th>
                <th className="px-3 py-2">{t('api_keys.table_prefix')}</th>
                <th className="px-3 py-2">{t('api_keys.table_tier')}</th>
                <th className="px-3 py-2">{t('api_keys.table_status')}</th>
                <th className="px-3 py-2">{t('api_keys.table_created')}</th>
                <th className="px-3 py-2">{t('api_keys.table_last_used')}</th>
                <th className="px-3 py-2">{t('api_keys.table_actions')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {keys.map((k) => (
                <tr key={k.id}>
                  <td className="px-3 py-2 font-medium">{k.label || '—'}</td>
                  <td className="px-3 py-2 font-mono text-xs">{k.key_prefix}…</td>
                  <td className="px-3 py-2">{k.tier}</td>
                  <td className="px-3 py-2">
                    {k.is_revoked ? (
                      <span className="text-red-700">{t('api_keys.status_revoked')}</span>
                    ) : (
                      <span className="text-emerald-700">{t('api_keys.status_active')}</span>
                    )}
                  </td>
                  <td className="px-3 py-2">{new Date(k.created_at).toLocaleDateString()}</td>
                  <td className="px-3 py-2">
                    {k.last_used_at ? new Date(k.last_used_at).toLocaleDateString() : '—'}
                  </td>
                  <td className="px-3 py-2">
                    {!k.is_revoked ? (
                      <button
                        onClick={() => void onRevoke(k.id)}
                        className="text-xs font-medium text-red-700 hover:underline"
                      >
                        {t('api_keys.revoke_cta')}
                      </button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function DomainsPanel() {
  const { t } = useTranslation();
  const { locale = 'uz' } = useParams();
  const [domains, setDomains] = useState<DomainRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [name, setName] = useState('');
  const [method, setMethod] = useState<DomainMethod>('dns_txt');
  const [notifyEmail, setNotifyEmail] = useState('');
  const [registering, setRegistering] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submittedTokens, setSubmittedTokens] = useState<Record<string, string>>({});
  const [verifying, setVerifying] = useState<string | null>(null);
  const [verifyError, setVerifyError] = useState<Record<string, string | null>>({});

  async function refresh() {
    setLoading(true);
    try {
      setDomains(await listDomains());
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function onRegister(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setRegistering(true);
    setError(null);
    try {
      const payload: Parameters<typeof registerDomain>[0] = {
        name: name.trim(),
        verification_method: method,
        locale,
      };
      if (method === 'email' && notifyEmail.trim()) {
        payload.notify_email = notifyEmail.trim();
      }
      await registerDomain(payload);
      setName('');
      setNotifyEmail('');
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setRegistering(false);
    }
  }

  async function onVerify(domain: DomainRow) {
    setVerifying(domain.id);
    setVerifyError((prev) => ({ ...prev, [domain.id]: null }));
    try {
      const submitted = submittedTokens[domain.id];
      const res = await verifyDomain(domain.id, submitted);
      if (res.status !== 'verified') {
        setVerifyError((prev) => ({
          ...prev,
          [domain.id]: t('account_domains.verify_failed', { detail: res.detail ?? '' }),
        }));
      }
      await refresh();
    } catch (err) {
      setVerifyError((prev) => ({
        ...prev,
        [domain.id]: err instanceof ApiError ? err.message : String(err),
      }));
    } finally {
      setVerifying(null);
    }
  }

  async function onDelete(id: string) {
    if (!confirm(t('account_domains.confirm_delete'))) return;
    await deleteDomain(id);
    await refresh();
  }

  return (
    <section className="space-y-6">
      <header className="space-y-1">
        <h2 className="text-lg font-semibold">{t('account_domains.title')}</h2>
        <p className="text-sm text-slate-600">{t('account_domains.subtitle')}</p>
      </header>

      <form className="grid gap-3 sm:grid-cols-[2fr,1fr,1fr,auto]" onSubmit={onRegister}>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          placeholder={t('account_domains.name_placeholder')}
          className="rounded-md border border-slate-300 px-3 py-2 text-sm"
        />
        <select
          value={method}
          onChange={(e) => setMethod(e.target.value as DomainMethod)}
          className="rounded-md border border-slate-300 px-3 py-2 text-sm"
        >
          <option value="dns_txt">{t('account_domains.method_dns')}</option>
          <option value="email">{t('account_domains.method_email')}</option>
          <option value="meta_tag">{t('account_domains.method_meta')}</option>
        </select>
        <input
          type="email"
          value={notifyEmail}
          onChange={(e) => setNotifyEmail(e.target.value)}
          placeholder={t('account_domains.notify_email_placeholder')}
          disabled={method !== 'email'}
          className="rounded-md border border-slate-300 px-3 py-2 text-sm disabled:bg-slate-100"
        />
        <button
          type="submit"
          disabled={registering}
          className="rounded-md bg-brand px-4 py-2 text-sm font-medium text-white hover:bg-brand-dark disabled:opacity-50"
        >
          {registering ? t('account_domains.registering') : t('account_domains.register_cta')}
        </button>
      </form>

      {error ? (
        <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900">{error}</div>
      ) : null}

      {loading ? (
        <p className="text-sm text-slate-600">{t('common.loading')}</p>
      ) : domains.length === 0 ? (
        <p className="rounded-md border border-dashed border-slate-300 px-4 py-6 text-center text-sm text-slate-600">
          {t('account_domains.empty')}
        </p>
      ) : (
        <ul className="space-y-4">
          {domains.map((d) => (
            <li key={d.id} className="space-y-3 rounded-md border border-slate-200 bg-white p-4 shadow-sm">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <div className="text-base font-semibold">{d.name}</div>
                  <div className="text-xs uppercase tracking-wide text-slate-500">
                    {t(`account_domains.method_${d.verification_method.replace('_tag', '').replace('_txt', '')}` as `account_domains.method_${'dns' | 'email' | 'meta'}`)}
                  </div>
                  <div className="mt-1 text-xs">
                    {d.verified_at ? (
                      <span className="text-emerald-700">{t('account_domains.verified')}</span>
                    ) : (
                      <span className="text-amber-700">{t('account_domains.pending')}</span>
                    )}
                  </div>
                </div>
                <button
                  onClick={() => void onDelete(d.id)}
                  className="text-xs font-medium text-red-700 hover:underline"
                >
                  {t('account_domains.delete_cta')}
                </button>
              </div>

              {!d.verified_at ? (
                <div className="space-y-3 rounded bg-slate-50 p-3 text-sm">
                  <div className="font-semibold text-slate-700">
                    {t('account_domains.instructions_title')}
                  </div>
                  {d.verification_method === 'dns_txt' ? (
                    <>
                      <p>{t('account_domains.instructions_dns')}</p>
                      <dl className="grid grid-cols-[auto,1fr] gap-x-3 gap-y-1 text-xs">
                        <dt className="font-medium">{t('account_domains.host')}</dt>
                        <dd className="font-mono">{d.instructions.host}</dd>
                        <dt className="font-medium">{t('account_domains.type')}</dt>
                        <dd className="font-mono">{d.instructions.type}</dd>
                        <dt className="font-medium">{t('account_domains.value')}</dt>
                        <dd className="font-mono break-all">{d.instructions.value}</dd>
                      </dl>
                    </>
                  ) : null}
                  {d.verification_method === 'meta_tag' ? (
                    <>
                      <p>{t('account_domains.instructions_meta')}</p>
                      <code className="block break-all rounded bg-white px-2 py-1 font-mono text-xs">
                        {d.instructions.tag}
                      </code>
                    </>
                  ) : null}
                  {d.verification_method === 'email' ? (
                    <>
                      <p>{t('account_domains.instructions_email')}</p>
                      <input
                        type="text"
                        value={submittedTokens[d.id] ?? ''}
                        onChange={(e) =>
                          setSubmittedTokens((prev) => ({ ...prev, [d.id]: e.target.value }))
                        }
                        placeholder={t('account_domains.submit_token_placeholder')}
                        className="w-full rounded border border-slate-300 px-2 py-1 text-xs"
                      />
                    </>
                  ) : null}

                  <div className="flex items-center gap-3">
                    <button
                      onClick={() => void onVerify(d)}
                      disabled={verifying === d.id}
                      className="rounded-md bg-brand px-3 py-1.5 text-xs font-medium text-white hover:bg-brand-dark disabled:opacity-50"
                    >
                      {verifying === d.id ? t('account_domains.verifying') : t('account_domains.verify_cta')}
                    </button>
                    {verifyError[d.id] ? (
                      <span className="text-xs text-red-700">{verifyError[d.id]}</span>
                    ) : null}
                  </div>
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
