import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { checkPassword } from '../lib/passwords';

const ORIGINAL_FETCH = globalThis.fetch;

describe('checkPassword (k-anonymity)', () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn(async (input) => {
      const url = typeof input === 'string' ? input : (input as Request).url;
      // SHA-1("hunter2") = F3BBBD66A63D4BF1747940578EC3D0103530E21D
      // Prefix F3BBB, suffix D66A63D4BF1747940578EC3D0103530E21D
      if (url.endsWith('/api/passwords/range/F3BBB')) {
        return new Response('D66A63D4BF1747940578EC3D0103530E21D:42\n0000000:1\n');
      }
      return new Response('', { status: 200 });
    }) as typeof fetch;
  });

  afterEach(() => {
    globalThis.fetch = ORIGINAL_FETCH;
    vi.restoreAllMocks();
  });

  it('returns count when suffix is found', async () => {
    const result = await checkPassword('hunter2');
    expect(result).toEqual({ count: 42 });
  });

  it('returns 0 when suffix is not found', async () => {
    const result = await checkPassword('a-password-that-is-very-unlikely');
    expect(result).toEqual({ count: 0 });
  });
});
