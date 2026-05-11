# Load tests

[k6](https://k6.io)-based load tests for the Xavfsizmi public API. These scripts
are not part of CI — they're meant to be run against a staging or production-like
environment from an operator's machine.

## Install k6

macOS:    `brew install k6`
Linux:    https://k6.io/docs/get-started/installation/
Windows:  `choco install k6`

## Scripts

| File | Goal |
|---|---|
| `k6-passwords.js` | Hammers the edge Worker (`/api/passwords/range/:prefix`) with random SHA-1 prefixes. Verifies the worker can absorb the burst (5xx and 429 are tracked as failure counters). |
| `k6-breached-account.js` | Authenticated public API — repeatedly looks up the same handful of throw-away accounts via `/v1/api/breachedaccount/{account}`. Tier limits are exercised by varying `XV_API_KEY`. |
| `k6-public-mix.js` | Mixed traffic: 70% passwords, 25% breach lookup, 5% breach detail. Closest to the shape we expect production to see. |

## Running

```bash
# Defaults: 10 VUs for 30s, base URL ``http://localhost:8000``.
k6 run load/k6-passwords.js

# Crank it up and point at staging:
BASE_URL=https://api.staging.xavfsizmi.example \
VUS=200 DURATION=2m \
  k6 run load/k6-public-mix.js

# Authenticated mix needs an API key:
BASE_URL=https://api.staging.xavfsizmi.example \
XV_API_KEY=xvf_live_xxx \
  k6 run load/k6-breached-account.js
```

## Thresholds

Each script declares thresholds that fail the run if exceeded:
- `http_req_failed{expected_response:true} < 1%`
- `http_req_duration{p(95)} < 500ms` (worker scripts) / `< 1s` (API scripts)
- Custom counters: `errors_5xx`, `errors_429`, `errors_4xx_other`

CI does **not** run these — they're a manual safety net before cutting a release.
