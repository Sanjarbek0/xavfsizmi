// k6 load script — production-shaped mixed traffic against the API + Worker.
//
// 70% passwords (worker), 25% breached-account (api), 5% breach detail (api).
// Use this one to validate end-to-end capacity before a release.

import http from 'k6/http';
import { check } from 'k6';
import { Counter, Trend } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const WORKER_URL = __ENV.WORKER_URL || 'http://localhost:8787';
const API_KEY = __ENV.XV_API_KEY;
const VUS = parseInt(__ENV.VUS || '50', 10);
const DURATION = __ENV.DURATION || '1m';

const errors5xx = new Counter('errors_5xx');
const errors4xx = new Counter('errors_4xx_other');
const ttfbPasswords = new Trend('ttfb_passwords', true);
const ttfbBreached = new Trend('ttfb_breached', true);

export const options = {
  vus: VUS,
  duration: DURATION,
  thresholds: {
    errors_5xx: ['count<25'],
    'http_req_duration{expected_response:true}': ['p(95)<1500'],
  },
};

const ACCOUNTS = [
  'loadtest+1@xavfsizmi.example',
  'loadtest+2@xavfsizmi.example',
  'loadtest+3@xavfsizmi.example',
];
const BREACHES = ['Adobe', 'LinkedIn', 'Dropbox'];

function rand5HexPrefix() {
  const n = Math.floor(Math.random() * 0x100000);
  return n.toString(16).toUpperCase().padStart(5, '0');
}

function track(res) {
  if (res.status >= 500) errors5xx.add(1);
  else if (res.status >= 400 && res.status !== 404) errors4xx.add(1);
}

export default function () {
  const roll = Math.random();
  if (roll < 0.7) {
    const res = http.get(`${WORKER_URL}/api/passwords/range/${rand5HexPrefix()}`);
    ttfbPasswords.add(res.timings.waiting);
    track(res);
    check(res, { 'passwords 200': (r) => r.status === 200 });
  } else if (roll < 0.95) {
    if (!API_KEY) return;
    const acc = ACCOUNTS[Math.floor(Math.random() * ACCOUNTS.length)];
    const res = http.get(
      `${BASE_URL}/v1/api/breachedaccount/${encodeURIComponent(acc)}`,
      { headers: { 'X-API-Key': API_KEY } },
    );
    ttfbBreached.add(res.timings.waiting);
    track(res);
    check(res, { 'breached 200 or 404': (r) => r.status === 200 || r.status === 404 });
  } else {
    const name = BREACHES[Math.floor(Math.random() * BREACHES.length)];
    const res = http.get(`${BASE_URL}/v1/breaches/${encodeURIComponent(name)}`);
    track(res);
    check(res, { 'breach 200 or 404': (r) => r.status === 200 || r.status === 404 });
  }
}
