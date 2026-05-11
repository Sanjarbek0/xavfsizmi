// k6 load script — authenticated /v1/api/breachedaccount/{account}.
//
// Requires XV_API_KEY in the env. The script alternates between a small set
// of probe emails so the API server (and its Redis cache) sees both cache
// hits and misses.

import http from 'k6/http';
import { check } from 'k6';
import { Counter } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const API_KEY = __ENV.XV_API_KEY;
const VUS = parseInt(__ENV.VUS || '10', 10);
const DURATION = __ENV.DURATION || '30s';

if (!API_KEY) {
  throw new Error('XV_API_KEY env var is required');
}

const errors5xx = new Counter('errors_5xx');
const errors429 = new Counter('errors_429');
const errors4xxOther = new Counter('errors_4xx_other');

export const options = {
  vus: VUS,
  duration: DURATION,
  thresholds: {
    'http_req_failed{expected_response:true}': ['rate<0.02'],
    'http_req_duration{expected_response:true}': ['p(95)<1000'],
    errors_5xx: ['count<5'],
  },
};

// Synthetic, non-existent addresses — we expect the upstream HIBP cache to
// return a small/empty payload very quickly. Replace with real probe accounts
// only against a staging environment you control.
const ACCOUNTS = [
  'loadtest+1@xavfsizmi.example',
  'loadtest+2@xavfsizmi.example',
  'loadtest+3@xavfsizmi.example',
  'loadtest+4@xavfsizmi.example',
];

export default function () {
  const account = ACCOUNTS[Math.floor(Math.random() * ACCOUNTS.length)];
  const url = `${BASE_URL}/v1/api/breachedaccount/${encodeURIComponent(account)}`;
  const res = http.get(url, {
    headers: { 'X-API-Key': API_KEY },
  });
  if (res.status >= 500) errors5xx.add(1);
  else if (res.status === 429) errors429.add(1);
  else if (res.status >= 400) errors4xxOther.add(1);
  check(res, {
    '200 or 404': (r) => r.status === 200 || r.status === 404,
    'tier header present': (r) => r.headers['X-Api-Tier'] !== undefined,
  });
}
