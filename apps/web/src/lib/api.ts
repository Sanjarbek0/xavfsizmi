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
    ...init,
  });
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
