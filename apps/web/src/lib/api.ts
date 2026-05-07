import type { AccountLookupResponse } from '@xavfsizmi/shared-types';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '';

export interface AccountLookupResult {
  breaches: { name: string; title?: string }[];
}

export async function lookupAccount(email: string): Promise<AccountLookupResult> {
  const res = await fetch(`${API_BASE}/v1/breaches/account`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
  });
  if (res.status === 404) return { breaches: [] };
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = (await res.json()) as AccountLookupResponse;
  return { breaches: data.breaches };
}
