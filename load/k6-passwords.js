// k6 load script — Pwned Passwords range endpoint (Cloudflare Worker).
//
// Generates a random 5-char hex prefix per iteration so we exercise the cache
// + R2 path realistically (sequential identical prefixes would just hit the
// edge cache and tell us nothing).
//
// Env: BASE_URL, VUS, DURATION, PREFIX_POOL.

import http from 'k6/http';
import { check } from 'k6';
import { Counter } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8787';
const VUS = parseInt(__ENV.VUS || '20', 10);
const DURATION = __ENV.DURATION || '30s';
const PREFIX_POOL = parseInt(__ENV.PREFIX_POOL || '4096', 10);

const errors5xx = new Counter('errors_5xx');
const errors429 = new Counter('errors_429');
const errors4xxOther = new Counter('errors_4xx_other');

export const options = {
  vus: VUS,
  duration: DURATION,
  thresholds: {
    'http_req_failed{expected_response:true}': ['rate<0.01'],
    'http_req_duration{expected_response:true}': ['p(95)<500'],
    errors_5xx: ['count<10'],
  },
};

// Pre-generate a pool of 5-char hex prefixes so we don't run Math.random in
// the hot path.
const PREFIXES = (() => {
  const out = new Array(PREFIX_POOL);
  for (let i = 0; i < PREFIX_POOL; i++) {
    out[i] = i.toString(16).toUpperCase().padStart(5, '0');
  }
  return out;
})();

export default function () {
  const prefix = PREFIXES[Math.floor(Math.random() * PREFIXES.length)];
  const res = http.get(`${BASE_URL}/api/passwords/range/${prefix}`, {
    headers: { 'Add-Padding': 'true' },
  });
  if (res.status >= 500) errors5xx.add(1);
  else if (res.status === 429) errors429.add(1);
  else if (res.status >= 400) errors4xxOther.add(1);
  check(res, {
    '200 OK': (r) => r.status === 200,
    'looks like hash list': (r) => /^[0-9A-F]{35}:\d+/m.test(r.body),
  });
}
