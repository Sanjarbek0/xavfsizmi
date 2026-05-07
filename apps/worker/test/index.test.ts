import { describe, expect, it, vi } from 'vitest';

import worker from '../src/index';
import type { Env } from '../src/index';

function fakeR2(map: Record<string, string>): R2Bucket {
  return {
    async get(key: string) {
      const v = map[key];
      if (!v) return null;
      return {
        text: async () => v,
        httpEtag: 'etag',
      } as unknown as R2ObjectBody;
    },
  } as unknown as R2Bucket;
}

function fakeCtx(): ExecutionContext {
  return {
    waitUntil: () => undefined,
    passThroughOnException: () => undefined,
    props: {},
  } as unknown as ExecutionContext;
}

const baseCaches = {
  default: {
    match: vi.fn().mockResolvedValue(undefined),
    put: vi.fn().mockResolvedValue(undefined),
  },
};
// @ts-expect-error — install the global stub
globalThis.caches = baseCaches;

describe('passwords range endpoint', () => {
  it('rejects bad prefix', async () => {
    const env: Env = { PWNED_PASSWORDS: fakeR2({}) };
    const res = await worker.fetch(
      new Request('https://w/api/passwords/range/ZZZZZ'),
      env,
      fakeCtx(),
    );
    expect(res.status).toBe(400);
  });

  it('returns SHA-1 range body verbatim', async () => {
    const env: Env = {
      PWNED_PASSWORDS: fakeR2({
        'sha1/ABCDE.txt': 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA:5',
      }),
    };
    const res = await worker.fetch(
      new Request('https://w/api/passwords/range/abcde'),
      env,
      fakeCtx(),
    );
    expect(res.status).toBe(200);
    expect(await res.text()).toBe('AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA:5');
  });

  it('returns NTLM range when mode=ntlm', async () => {
    const env: Env = {
      PWNED_PASSWORDS: fakeR2({
        'ntlm/12345.txt': 'BBBBBBBBBBBBBBBBBBBBBBBBBB:7',
      }),
    };
    const res = await worker.fetch(
      new Request('https://w/api/passwords/range/12345?mode=ntlm'),
      env,
      fakeCtx(),
    );
    expect(res.status).toBe(200);
    expect(await res.text()).toContain(':7');
  });

  it('rejects non-GET methods', async () => {
    const env: Env = { PWNED_PASSWORDS: fakeR2({}) };
    const res = await worker.fetch(
      new Request('https://w/api/passwords/range/ABCDE', { method: 'POST' }),
      env,
      fakeCtx(),
    );
    expect(res.status).toBe(405);
  });
});
