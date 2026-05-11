import type {
  AccountLookupResponse,
  BreachSummary,
  NotificationSubscribeResponse,
  PasteLookupResponse,
  PasteSummary,
  ProblemDetails,
} from '@xavfsizmi/shared-types';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '';

export class ApiError extends Error {
  readonly status: number;
  readonly problem: ProblemDetails | undefined;

  constructor(status: number, message: string, problem?: ProblemDetails) {
    super(message);
    this.status = status;
    this.problem = problem;
  }
}

async function readProblem(res: Response): Promise<ProblemDetails | undefined> {
  const ct = res.headers.get('content-type') ?? '';
  if (!ct.includes('json')) return undefined;
  try {
    return (await res.json()) as ProblemDetails;
  } catch {
    return undefined;
  }
}

async function callJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', Accept: 'application/json', ...(init?.headers ?? {}) },
    credentials: 'include',
    ...init,
  });
  if (res.status === 204) return undefined as T;
  if (!res.ok) {
    const problem = await readProblem(res);
    const message = problem?.detail ?? problem?.title ?? `HTTP ${res.status}`;
    throw new ApiError(res.status, message, problem);
  }
  return (await res.json()) as T;
}

interface RawBreach {
  name: string;
  title?: string | null;
  domain?: string | null;
  breach_date?: string | null;
  pwn_count?: number | null;
  is_verified?: boolean | null;
  is_sensitive?: boolean | null;
  is_fabricated?: boolean | null;
  is_retired?: boolean | null;
  is_spam_list?: boolean | null;
  description?: string | null;
  data_classes?: string[] | null;
  logo_path?: string | null;
}

interface RawAccountLookup {
  email: string;
  breaches: RawBreach[];
  cached?: boolean;
}

interface RawPaste {
  source: string;
  id: string;
  title?: string | null;
  date?: string | null;
  email_count?: number | null;
}

interface RawPasteLookup {
  email: string;
  pastes: RawPaste[];
  cached?: boolean;
}

function defined<T>(value: T | null | undefined): T | undefined {
  return value === null || value === undefined ? undefined : value;
}

function assignOptional<T extends object, K extends keyof T>(
  target: T,
  key: K,
  value: T[K] | undefined,
): void {
  if (value !== undefined) target[key] = value;
}

function mapBreach(b: RawBreach): BreachSummary {
  const result: BreachSummary = { name: b.name };
  assignOptional(result, 'title', defined(b.title));
  assignOptional(result, 'domain', defined(b.domain));
  assignOptional(result, 'breachDate', defined(b.breach_date));
  assignOptional(result, 'pwnCount', defined(b.pwn_count));
  assignOptional(result, 'isVerified', defined(b.is_verified));
  assignOptional(result, 'isSensitive', defined(b.is_sensitive));
  assignOptional(result, 'isFabricated', defined(b.is_fabricated));
  assignOptional(result, 'isRetired', defined(b.is_retired));
  assignOptional(result, 'isSpamList', defined(b.is_spam_list));
  assignOptional(result, 'description', defined(b.description));
  assignOptional(result, 'dataClasses', defined(b.data_classes));
  assignOptional(result, 'logoPath', defined(b.logo_path));
  return result;
}

function mapPaste(p: RawPaste): PasteSummary {
  const result: PasteSummary = { source: p.source, id: p.id };
  assignOptional(result, 'title', defined(p.title));
  assignOptional(result, 'date', defined(p.date));
  assignOptional(result, 'emailCount', defined(p.email_count));
  return result;
}

export async function lookupAccount(
  email: string,
  options: { turnstileToken?: string | null; includeUnverified?: boolean } = {},
): Promise<AccountLookupResponse> {
  const raw = await callJson<RawAccountLookup>('/v1/breaches/account', {
    method: 'POST',
    body: JSON.stringify({
      email,
      turnstileToken: options.turnstileToken ?? null,
      includeUnverified: options.includeUnverified ?? true,
    }),
  });
  const result: AccountLookupResponse = {
    email: raw.email,
    breaches: raw.breaches.map(mapBreach),
  };
  if (raw.cached !== undefined) result.cached = raw.cached;
  return result;
}

export async function listBreaches(domain?: string): Promise<BreachSummary[]> {
  const qs = domain ? `?domain=${encodeURIComponent(domain)}` : '';
  const raw = await callJson<RawBreach[]>(`/v1/breaches${qs}`);
  return raw.map(mapBreach);
}

export async function getBreach(name: string): Promise<BreachSummary> {
  const raw = await callJson<RawBreach>(`/v1/breaches/${encodeURIComponent(name)}`);
  return mapBreach(raw);
}

export async function lookupPastes(
  email: string,
  options: { turnstileToken?: string | null } = {},
): Promise<PasteLookupResponse> {
  const raw = await callJson<RawPasteLookup>('/v1/breaches/paste', {
    method: 'POST',
    body: JSON.stringify({ email, turnstileToken: options.turnstileToken ?? null }),
  });
  const result: PasteLookupResponse = {
    email: raw.email,
    pastes: raw.pastes.map(mapPaste),
  };
  if (raw.cached !== undefined) result.cached = raw.cached;
  return result;
}

export async function subscribeNotifications(
  email: string,
  locale: string,
  turnstileToken?: string | null,
): Promise<NotificationSubscribeResponse> {
  return callJson<NotificationSubscribeResponse>('/v1/notifications/subscribe', {
    method: 'POST',
    body: JSON.stringify({ email, locale, turnstileToken: turnstileToken ?? null }),
  });
}

export interface AuthRequestResponse {
  status: string;
  message: string;
  locale: string;
}

export interface CurrentUser {
  user_id: string;
  email: string;
  is_admin: boolean;
  last_login_at: string | null;
}

export async function requestMagicLink(
  email: string,
  locale: string,
  turnstileToken?: string | null,
  redirectPath?: string,
): Promise<AuthRequestResponse> {
  return callJson<AuthRequestResponse>('/v1/auth/request', {
    method: 'POST',
    body: JSON.stringify({
      email,
      locale,
      turnstileToken: turnstileToken ?? null,
      redirectPath: redirectPath ?? null,
    }),
  });
}

export async function verifyMagicLink(token: string): Promise<CurrentUser> {
  const res = await callJson<{
    status: string;
    user_id: string;
    email: string;
    is_admin: boolean;
  }>('/v1/auth/verify', {
    method: 'POST',
    body: JSON.stringify({ token }),
  });
  return {
    user_id: res.user_id,
    email: res.email,
    is_admin: res.is_admin,
    last_login_at: null,
  };
}

export async function logout(): Promise<void> {
  await callJson<{ status: string }>('/v1/auth/logout', { method: 'POST' });
}

export async function fetchMe(): Promise<CurrentUser | null> {
  try {
    return await callJson<CurrentUser>('/v1/auth/me');
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) return null;
    throw err;
  }
}

export type ApiKeyTier = 'free' | 'pro' | 'high_rpm';

export interface ApiKeyRow {
  id: string;
  label: string;
  key_prefix: string;
  tier: ApiKeyTier;
  is_revoked: boolean;
  created_at: string;
  last_used_at: string | null;
}

export async function listApiKeys(): Promise<ApiKeyRow[]> {
  const res = await callJson<{ items: ApiKeyRow[] }>('/v1/account/api-keys');
  return res.items;
}

export async function createApiKey(
  label: string,
  tier: ApiKeyTier | null = null,
): Promise<{ key: ApiKeyRow; plaintext: string }> {
  return callJson<{ key: ApiKeyRow; plaintext: string }>('/v1/account/api-keys', {
    method: 'POST',
    body: JSON.stringify({ label, tier }),
  });
}

export async function revokeApiKey(id: string): Promise<void> {
  await callJson<void>(`/v1/account/api-keys/${id}`, { method: 'DELETE' });
}

export type DomainMethod = 'dns_txt' | 'email' | 'meta_tag';

export interface DomainRow {
  id: string;
  name: string;
  verification_method: DomainMethod;
  verification_token: string;
  verified_at: string | null;
  created_at: string;
  instructions: Record<string, string>;
}

export async function listDomains(): Promise<DomainRow[]> {
  const res = await callJson<{ items: DomainRow[] }>('/v1/account/domains');
  return res.items;
}

export async function registerDomain(payload: {
  name: string;
  verification_method: DomainMethod;
  locale: string;
  notify_email?: string;
}): Promise<DomainRow> {
  const res = await callJson<{ domain: DomainRow }>('/v1/account/domains', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  return res.domain;
}

export async function verifyDomain(id: string, submittedToken?: string): Promise<{
  status: 'verified' | 'failed' | 'pending';
  detail: string | null;
  domain: DomainRow;
}> {
  return callJson(`/v1/account/domains/${id}/verify`, {
    method: 'POST',
    body: JSON.stringify({ submitted_token: submittedToken ?? null }),
  });
}

export async function deleteDomain(id: string): Promise<void> {
  await callJson<void>(`/v1/account/domains/${id}`, { method: 'DELETE' });
}

export interface TokenActionResponse {
  status: string;
  message: string;
}

export async function confirmNotification(token: string): Promise<TokenActionResponse> {
  return callJson<TokenActionResponse>('/v1/notifications/confirm', {
    method: 'POST',
    body: JSON.stringify({ token }),
  });
}

export async function unsubscribeNotification(token: string): Promise<TokenActionResponse> {
  return callJson<TokenActionResponse>('/v1/notifications/unsubscribe', {
    method: 'POST',
    body: JSON.stringify({ token }),
  });
}

export interface UsagePoint {
  day: string;
  request_count: number;
}

export interface ApiKeyUsage {
  items: UsagePoint[];
  total: number;
  today: number;
  current_minute: number;
  tier: ApiKeyTier;
  requests_per_minute: number;
  remaining_this_minute: number;
}

export async function fetchApiKeyUsage(id: string, days = 30): Promise<ApiKeyUsage> {
  return callJson<ApiKeyUsage>(`/v1/account/api-keys/${id}/usage?days=${days}`);
}

export interface TierLimit {
  tier: ApiKeyTier;
  requests_per_minute: number;
}

export interface SubscriptionStatus {
  tier: string;
  status: string;
  current_period_end: string | null;
  has_customer: boolean;
  available_tiers: TierLimit[];
}

export async function fetchSubscription(): Promise<SubscriptionStatus> {
  return callJson<SubscriptionStatus>('/v1/account/billing/subscription');
}

export interface CheckoutPayload {
  tier: 'pro' | 'high_rpm';
  successPath?: string;
  cancelPath?: string;
}

export async function startCheckout(payload: CheckoutPayload): Promise<{ checkout_url: string; session_id: string }> {
  return callJson('/v1/account/billing/checkout', {
    method: 'POST',
    body: JSON.stringify({
      tier: payload.tier,
      success_path: payload.successPath ?? null,
      cancel_path: payload.cancelPath ?? null,
    }),
  });
}

export async function openBillingPortal(): Promise<{ portal_url: string }> {
  return callJson('/v1/account/billing/portal', { method: 'POST' });
}

export interface AdminMetrics {
  user_count: number;
  api_key_count: number;
  domain_count: number;
  notification_subscriber_count: number;
  cached_breach_count: number;
}

export async function fetchAdminMetrics(): Promise<AdminMetrics> {
  return callJson<AdminMetrics>('/v1/admin/metrics');
}

export interface AdminUserRow {
  id: string;
  email: string;
  is_admin: boolean;
  is_blocked: boolean;
  created_at: string;
  last_login_at: string | null;
}

export async function fetchAdminUsers(): Promise<AdminUserRow[]> {
  const res = await callJson<{ users: AdminUserRow[] }>('/v1/admin/users');
  return res.users;
}

export async function setUserBlocked(userId: string, blocked: boolean): Promise<AdminUserRow> {
  return callJson<AdminUserRow>(`/v1/admin/users/${userId}/block`, {
    method: 'POST',
    body: JSON.stringify({ blocked }),
  });
}

export interface AdminAuditRow {
  id: number;
  actor_user_id: string | null;
  actor_ip: string | null;
  action: string;
  target_type: string | null;
  target_id: string | null;
  detail: Record<string, unknown> | null;
  created_at: string;
}

export async function fetchAdminAudit(limit = 100): Promise<AdminAuditRow[]> {
  const res = await callJson<{ entries: AdminAuditRow[] }>(`/v1/admin/audit?limit=${limit}`);
  return res.entries;
}

export interface AdminBreachRow {
  name: string;
  title: string | null;
  domain: string | null;
  breach_date: string | null;
  pwn_count: number | null;
  is_verified: boolean | null;
  is_sensitive: boolean | null;
  description: string | null;
  data_classes: string[] | null;
}

export async function fetchAdminBreaches(): Promise<AdminBreachRow[]> {
  const res = await callJson<{ breaches: AdminBreachRow[] }>('/v1/admin/breaches');
  return res.breaches;
}

export async function upsertAdminBreach(payload: AdminBreachRow): Promise<AdminBreachRow> {
  return callJson<AdminBreachRow>('/v1/admin/breaches', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}
