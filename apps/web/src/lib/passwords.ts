const PASSWORDS_BASE = import.meta.env.VITE_PASSWORDS_BASE_URL ?? '';

export interface PasswordCheckResult {
  count: number;
}

/**
 * Checks a password using k-anonymity. The full password is never sent —
 * only the first 5 hex chars of its SHA-1 hash. The remaining 35 chars
 * are matched locally against the response.
 */
export async function checkPassword(password: string): Promise<PasswordCheckResult> {
  const hash = await sha1Hex(password);
  const prefix = hash.slice(0, 5).toUpperCase();
  const suffix = hash.slice(5).toUpperCase();

  const res = await fetch(`${PASSWORDS_BASE}/api/passwords/range/${prefix}`, {
    headers: { 'Add-Padding': 'true' },
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const body = await res.text();

  for (const line of body.split('\n')) {
    const [s, c] = line.trim().split(':');
    if (s === suffix) {
      const n = Number.parseInt(c ?? '0', 10);
      return { count: Number.isFinite(n) ? n : 0 };
    }
  }
  return { count: 0 };
}

async function sha1Hex(input: string): Promise<string> {
  const data = new TextEncoder().encode(input);
  const digest = await crypto.subtle.digest('SHA-1', data);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}
