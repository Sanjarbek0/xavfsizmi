/**
 * Xavfsizmi — Pwned Passwords k-anonymity endpoint.
 *
 * Serves SHA-1 / NTLM hash-prefix range files from R2:
 *   GET /api/passwords/range/:prefix              (SHA-1)
 *   GET /api/passwords/range/:prefix?mode=ntlm    (NTLM)
 *
 * The full password is never sent. Clients hash locally, send the first
 * 5 hex chars of the hash, and match the remaining chars against the
 * response body.
 */

export interface Env {
  PWNED_PASSWORDS: R2Bucket;
  PADDING_MAX?: string;
}

const PREFIX_RE = /^[0-9A-F]{5}$/i;
const RANGE_PATH = /^\/api\/passwords\/range\/([^/?#]+)\/?$/;

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    if (request.method === 'OPTIONS') return cors(new Response(null, { status: 204 }));
    if (request.method !== 'GET') {
      return cors(problem(405, 'method_not_allowed', 'GET only.'));
    }

    const url = new URL(request.url);
    const match = url.pathname.match(RANGE_PATH);
    const rawPrefix = match?.[1];
    if (!rawPrefix) return cors(problem(404, 'not_found', 'Unknown route.'));

    const prefix = rawPrefix.toUpperCase();
    if (!PREFIX_RE.test(prefix)) {
      return cors(problem(400, 'bad_prefix', 'Prefix must be 5 hex chars.'));
    }

    const mode = url.searchParams.get('mode') === 'ntlm' ? 'ntlm' : 'sha1';
    const wantsPadding = request.headers.get('Add-Padding') === 'true';
    const cacheKey = new Request(`${url.origin}/_cache/${mode}/${prefix}`, request);
    const cache = (caches as unknown as { default: Cache }).default;

    const cached = await cache.match(cacheKey);
    if (cached) return cors(cached);

    const objectKey = mode === 'ntlm' ? `ntlm/${prefix}.txt` : `sha1/${prefix}.txt`;
    const obj = await env.PWNED_PASSWORDS.get(objectKey);
    if (!obj) {
      const empty = wantsPadding ? padBody('', env) : '';
      const res = new Response(empty, {
        status: 200,
        headers: {
          'content-type': 'text/plain; charset=utf-8',
          'cache-control': 'public, max-age=86400',
        },
      });
      ctx.waitUntil(cache.put(cacheKey, res.clone()));
      return cors(res);
    }

    let body = await obj.text();
    if (wantsPadding) body = padBody(body, env);

    const res = new Response(body, {
      status: 200,
      headers: {
        'content-type': 'text/plain; charset=utf-8',
        'cache-control': 'public, max-age=86400',
        etag: obj.httpEtag,
      },
    });
    ctx.waitUntil(cache.put(cacheKey, res.clone()));
    return cors(res);
  },
};

function padBody(body: string, env: Env): string {
  const max = Number.parseInt(env.PADDING_MAX ?? '800', 10);
  const realLines = body ? body.split('\n').filter(Boolean) : [];
  const target = realLines.length + Math.floor(Math.random() * Math.max(1, max - realLines.length));
  const padded = [...realLines];
  for (let i = realLines.length; i < target; i++) {
    padded.push(`${randomHex(35)}:0`);
  }
  return padded.join('\n');
}

function randomHex(length: number): string {
  const bytes = new Uint8Array(Math.ceil(length / 2));
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0'))
    .join('')
    .slice(0, length)
    .toUpperCase();
}

function cors(res: Response): Response {
  const out = new Response(res.body, res);
  out.headers.set('access-control-allow-origin', '*');
  out.headers.set('access-control-allow-methods', 'GET, OPTIONS');
  out.headers.set('access-control-allow-headers', 'Add-Padding');
  out.headers.set('access-control-max-age', '86400');
  return out;
}

function problem(status: number, title: string, detail: string): Response {
  return new Response(JSON.stringify({ status, title, detail }), {
    status,
    headers: { 'content-type': 'application/problem+json' },
  });
}
