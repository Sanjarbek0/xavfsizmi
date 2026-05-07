# Xavfsizmi — Architecture

**Slogan**
- 🇺🇿 Sizning ma'lumotlaringiz xavfsizmi?
- 🇷🇺 Ваши данные в безопасности?
- 🇬🇧 Is your data safe?

> Multilingual (uz-Latn, ru, en) breach-lookup service inspired by the
> publicly documented patterns of HaveIBeenPwned (HIBP). Self-hosted
> Pwned Passwords (k-anonymity SHA-1 prefix lookup) plus a HIBP v3 API
> proxy for email/breach/paste/domain search.

This document is the contract: it captures the goals, scope, technology
choices, system topology, data flow, data model, API surface, security
posture, and rollout plan. Everything else in the repo follows it.

---

## 1. Goals & non-goals

### Goals
1. Let any user check whether an email or password has appeared in a
   known data breach, with privacy preserved.
2. Provide the full HIBP-style feature set (email search, domain search,
   pastes, notifications, public API, admin) at parity with the public
   model.
3. Be fully usable in **Uzbek (Latin)**, **Russian**, and **English**.
4. Support a paid public API (Stripe) and a free, rate-limited tier.
5. Be operable by one person; observable; cheap to run at low traffic.
6. Be brand-swappable: the name "Xavfsizmi" must be replaceable in one
   config change.

### Non-goals (for v1)
- Native mobile apps (responsive web only).
- Stealer-log search beyond what the HIBP API exposes us.
- Operating our own breach corpus at HIBP scale; we lean on HIBP's
  authenticated API for breach/paste/domain data and only self-host the
  Pwned Passwords k-anonymity dataset.
- On-prem / air-gapped deployment.

---

## 2. High-level topology

```
                            ┌────────────────────┐
                            │ Cloudflare (DNS,    │
                            │ TLS, WAF, Turnstile,│
                            │ R2, Workers)        │
                            └─────────┬──────────┘
                                      │
   ┌──────────────────────────────────┼────────────────────────────┐
   │                                  │                            │
   ▼                                  ▼                            ▼
┌──────────────┐             ┌────────────────────┐       ┌───────────────────┐
│ apps/web     │             │ apps/worker        │       │ apps/api          │
│ Vite + React │             │ Cloudflare Worker  │       │ FastAPI (Python)  │
│ + i18next    │             │ Pwned Passwords    │       │                   │
│ + Tailwind   │   /api/*    │ k-anonymity:       │       │ /v1/breaches/*    │
│              │────────────▶│ /range/{prefix}    │       │ /v1/pastes/*      │
│ uz/ru/en     │             │ + /verify/{prefix} │       │ /v1/domains/*     │
│ URL prefix + │             │  (NTLM)            │       │ /v1/notifications │
│ cookie       │             │                    │       │ /v1/api-keys/*    │
└──────┬───────┘             │ Static dataset on  │       │ /v1/admin/*       │
       │                     │ Cloudflare R2:     │       │ /healthz          │
       │ static page         │   /pp/<prefix>.txt │       └────────┬──────────┘
       │ assets via CDN      └────────────────────┘                │
       │                                                           │
       │                                                           ▼
       │                                                 ┌───────────────────┐
       │                                                 │ HIBP API v3       │
       │                                                 │ haveibeenpwned.com│
       │                                                 │ + hibp-api-key    │
       │                                                 └───────────────────┘
       │
       ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  ┌──────────────┐
│ PostgreSQL   │  │ Redis        │  │ SMTP relay       │  │ Stripe API   │
│ - users      │  │ - cache      │  │ (notifications)  │  │ (billing)    │
│ - api_keys   │  │ - rate-limit │  └──────────────────┘  └──────────────┘
│ - notif subs │  │ - HIBP cache │
│ - domains    │  └──────────────┘
│ - breaches*  │
│ - pastes*    │
└──────────────┘
* breaches/pastes are mirror tables (cache of HIBP responses) plus
  optional locally-curated entries for breaches not in HIBP.
```

### Why this split
- **`apps/web`** is a stateless SPA served from Cloudflare Pages (or any
  static host). All sensitive logic is server-side.
- **`apps/worker`** owns the Pwned Passwords endpoint. It serves a
  ~40 GB SHA-1 hash range dataset directly from Cloudflare R2 with
  Cache API in front, so passwords lookups never hit our origin and
  cost almost nothing per request.
- **`apps/api`** owns everything that needs a database, secret keys, or
  the HIBP API: account-level breach search, domain search, email
  notifications, API-key issuance, billing, admin.
- **HIBP** is the source of truth for breach metadata, paste data, and
  account/domain breach lookups. We never re-publish the underlying
  email lists; we only return "found"/"not found" plus public breach
  metadata as the HIBP licence allows.

---

## 3. Repository layout (monorepo)

```
xavfsizmi/
├── ARCHITECTURE.md          ← this file
├── README.md
├── LICENSE                  ← proprietary (private repo)
├── package.json             ← pnpm + turbo orchestration
├── pnpm-workspace.yaml
├── turbo.json
├── .editorconfig
├── .gitignore
├── .github/workflows/ci.yml
├── apps/
│   ├── web/                 ← Vite + React + i18next + Tailwind
│   ├── api/                 ← FastAPI (uv-managed)
│   └── worker/              ← Cloudflare Worker (TypeScript)
├── packages/
│   ├── shared-types/        ← TS DTOs shared by web + worker
│   ├── i18n-data/           ← canonical translations (uz/ru/en)
│   └── eslint-config/
├── infra/
│   ├── docker-compose.yml   ← Postgres + Redis for local dev
│   ├── Dockerfile.api
│   └── Dockerfile.web
└── scripts/
    ├── ingest_pwned_passwords.py
    └── translate.ts         ← machine-translation pass for i18n keys
```

### Why pnpm + turbo + uv (and not "one tool to rule them all")
- pnpm workspaces handle the JS/TS half (`web`, `worker`,
  `packages/*`).
- uv handles `apps/api` as a separate Python project with a lockfile.
- Turbo orchestrates `lint`, `typecheck`, `test`, `build` across both
  worlds via plain shell tasks. There is no JS↔Python dependency
  graph, only a parallel-task scheduler.

---

## 4. Languages & i18n

### Decisions
- **Locales:** `uz` (Latin), `ru`, `en`. Default: `uz`.
- **Routing:** **hybrid** — URL prefix (`/uz/...`, `/ru/...`,
  `/en/...`) is canonical for SEO/`hreflang`, plus a `xv_lang` cookie
  that records the user's preferred language so the unprefixed root
  redirects to the right locale.
- **Translation pipeline:**
  1. Source-of-truth keys live in `packages/i18n-data/src/<locale>/*.json`
     in `en` first.
  2. `scripts/translate.ts` performs a machine-translation pass for
     `uz` and `ru` and writes the result with a `_machine: true` flag.
  3. A human review pass clears the flag once a translator approves.
- **`hreflang`:** every page emits
  `<link rel="alternate" hreflang="uz" href="…/uz/…" />` for all three
  locales plus `x-default`. Sitemap lists each URL three times.
- **Email templates:** rendered server-side from `apps/api`'s
  `translations/<locale>/emails/*.mjml` plus the same JSON catalogue.

### Locale negotiation
1. If URL has a locale prefix → use it.
2. Else if `xv_lang` cookie is set and valid → 302 redirect to
   `/{xv_lang}/...`.
3. Else if `Accept-Language` matches one of our locales → 302 redirect.
4. Else default to `/uz/...`.

---

## 5. Data flow per feature

### 5.1 Email breach search (privacy-preserving)
1. User types email on `/{locale}/`.
2. Frontend solves Cloudflare Turnstile.
3. Frontend POSTs `{ email, turnstile_token }` to
   `POST /v1/breaches/account` on `apps/api`.
4. API verifies Turnstile, applies per-IP rate limit (Redis), then
   either:
   - calls HIBP `GET /breachedaccount/{email}?truncateResponse=true`
     using `hibp-api-key`, **or**
   - calls HIBP's k-anonymity range endpoint
     `GET /breachedaccount/range/{sha1-prefix}` and matches the suffix
     locally (the privacy-preserving path; preferred for non-logged-in
     visitors).
5. API caches the response in Redis for ~10 min keyed by `sha256(email)`.
6. API returns a list of breach summaries; the frontend renders the
   familiar "Oh no — pwned!" / "Good news — no pwnage found!" UX
   adapted into Uzbek/Russian/English.

### 5.2 Pwned Passwords (k-anonymity)
1. User types a password into `/{locale}/passwords`.
2. Browser computes `sha1(password).toUpperCase()` **locally** and
   sends only the first 5 chars to `apps/worker`:
   `GET /api/passwords/range/{prefix}` (with optional
   `Add-Padding: true` header).
3. Worker reads `r2://pwned-passwords/<prefix>.txt` (cached at the
   Cloudflare edge) and returns the body verbatim — a list of
   `<35-char-suffix>:<count>` lines.
4. Browser scans the response for the remaining 35 chars. If found,
   shows the count and the explainer; otherwise shows "good".
5. NTLM has the symmetric `/api/passwords/range/{prefix}?mode=ntlm`
   path served from `r2://pwned-passwords/ntlm/<prefix>.txt`.

The full password is **never** sent anywhere. The privacy explainer
page documents this exactly.

### 5.3 Domain search
1. User adds a domain on `/{locale}/domains`.
2. We require ownership verification via one of three methods:
   - **DNS TXT:** publish `xavfsizmi-verify=<token>` at the apex.
   - **Email confirmation:** click a link sent to one of
     `admin@`, `administrator@`, `hostmaster@`, `postmaster@`,
     `webmaster@`.
   - **Meta tag:** put `<meta name="xavfsizmi-verify" content="…">` on
     the apex's homepage.
3. After verification, the API issues a polling task that calls HIBP
   `GET /breaches?Domain={d}` and `GET /breachedDomain/{d}` (the latter
   needs the appropriate plan) and stores the result in PostgreSQL.
4. The user gets a dashboard listing breached email addresses on their
   domain plus a CSV export.

### 5.4 Notifications
1. User submits email on `/{locale}/notifications`.
2. We send a double opt-in confirmation email in the user's locale via
   SMTP.
3. On click, we record a row in `notification_subs(email_hash, locale,
   confirmed_at)`.
4. A daily worker compares the latest HIBP "all breaches" feed against
   each subscriber's hashed email (using k-anonymity range lookups)
   and sends out localised "your address appears in <breach>" emails.

### 5.5 Public API
1. User signs up at `/{locale}/api`, creates an account (magic-link
   email login — no passwords on our side either).
2. They pick a tier (Free / Pro / High RPM). Stripe Checkout for paid
   tiers; a webhook activates the API key.
3. API keys are 32-byte URL-safe tokens, hashed with Argon2id at rest.
4. Requests authenticate via `xavfsizmi-api-key: <key>` and are
   rate-limited per key in Redis (token bucket).

### 5.6 Admin
- `/admin` is gated by an allow-list in env (`ADMIN_EMAILS`) plus
  TOTP. Magic-link login flow; no password.
- Admin can: upload locally-curated breach metadata (for breaches not
  in HIBP), retire breaches, ban API keys, inspect rate-limit state,
  re-run HIBP cache invalidation, change the brand name/logo via the
  `branding` settings table.

---

## 6. Data model (PostgreSQL)

Schema names use snake_case. Every table has `id UUID PRIMARY KEY
DEFAULT gen_random_uuid()`, `created_at TIMESTAMPTZ DEFAULT now()`,
`updated_at TIMESTAMPTZ DEFAULT now()` unless noted.

```sql
-- branding ---------------------------------------------------
branding (
  id           UUID PK,
  key          TEXT UNIQUE,        -- 'name', 'logo_url', 'primary_color'
  value        TEXT
)

-- accounts ---------------------------------------------------
users (
  id           UUID PK,
  email        CITEXT UNIQUE NOT NULL,
  email_hash   BYTEA NOT NULL,     -- sha256(lower(email))
  locale       TEXT NOT NULL DEFAULT 'uz',
  is_admin     BOOLEAN NOT NULL DEFAULT false,
  totp_secret  BYTEA,              -- nullable until enrolled
  last_login   TIMESTAMPTZ
)

magic_link_tokens (
  id           UUID PK,
  user_id      UUID FK users(id),
  token_hash   BYTEA UNIQUE,       -- sha256(token)
  expires_at   TIMESTAMPTZ NOT NULL,
  consumed_at  TIMESTAMPTZ
)

-- API keys ---------------------------------------------------
api_keys (
  id           UUID PK,
  user_id      UUID FK users(id),
  key_hash     BYTEA UNIQUE,       -- argon2id(key)
  prefix       TEXT NOT NULL,      -- first 8 chars for display
  tier         TEXT NOT NULL,      -- 'free' | 'pro' | 'high_rpm'
  rpm          INT  NOT NULL,
  monthly_cap  INT,
  stripe_sub   TEXT,
  revoked_at   TIMESTAMPTZ
)

api_key_usage (
  id           BIGSERIAL PK,
  api_key_id   UUID FK api_keys(id),
  ts_minute    TIMESTAMPTZ,        -- truncated to minute
  count        INT
)

-- domains ----------------------------------------------------
domains (
  id           UUID PK,
  user_id      UUID FK users(id),
  domain       TEXT NOT NULL,
  verified_at  TIMESTAMPTZ,
  verify_method TEXT,              -- 'dns_txt' | 'email' | 'meta'
  verify_token TEXT,
  UNIQUE (user_id, domain)
)

-- notifications ---------------------------------------------
notification_subs (
  id           UUID PK,
  email        CITEXT,
  email_hash   BYTEA NOT NULL,     -- sha256(lower(email))
  locale       TEXT NOT NULL DEFAULT 'uz',
  confirm_token_hash BYTEA UNIQUE,
  confirmed_at TIMESTAMPTZ,
  unsubscribe_token_hash BYTEA UNIQUE
)

-- HIBP cache (mirror) ---------------------------------------
breaches (
  id           UUID PK,
  name         TEXT UNIQUE,        -- HIBP "Name" field
  payload      JSONB NOT NULL,     -- full HIBP breach model
  source       TEXT NOT NULL DEFAULT 'hibp',  -- 'hibp' | 'local'
  fetched_at   TIMESTAMPTZ
)

paste_cache (
  id           UUID PK,
  email_hash   BYTEA NOT NULL,
  payload      JSONB NOT NULL,
  fetched_at   TIMESTAMPTZ,
  UNIQUE (email_hash)
)

-- audit ------------------------------------------------------
audit_log (
  id           BIGSERIAL PK,
  ts           TIMESTAMPTZ DEFAULT now(),
  actor_id     UUID,
  action       TEXT,
  payload      JSONB
)
```

### Redis keyspace
```
rl:ip:<sha256(ip)>:<route>          → token-bucket counter, 1-min TTL
rl:key:<api_key_id>                 → token-bucket counter
cache:breach:<email_hash>           → JSON, 600s TTL
cache:paste:<email_hash>            → JSON, 600s TTL
turnstile:replay:<token_hash>       → "1", 5-min TTL
session:<id>                        → JSON for short-lived flows
```

---

## 7. Public API surface

All routes are versioned at `/v1`. JSON I/O. Errors follow RFC 7807
(`application/problem+json`). All error messages are localised via the
`Accept-Language` header (or `?lang=` override).

### Open (no auth, Turnstile required for write paths)
```
POST /v1/breaches/account             body: {email}
POST /v1/breaches/account/range       body: {prefix6}    # k-anon mirror
GET  /v1/breaches                     query: ?domain=&isVerified=
GET  /v1/breaches/{name}
GET  /v1/data-classes
POST /v1/notifications/subscribe      body: {email, locale}
POST /v1/notifications/confirm        body: {token}
POST /v1/notifications/unsubscribe    body: {token}
GET  /healthz
GET  /metrics                         # Prometheus, behind allow-list
```

### Authenticated (`xavfsizmi-api-key` header)
```
GET  /v1/breachedaccount/{email}      # full HIBP-style response
GET  /v1/pastes/{email}
POST /v1/domains
POST /v1/domains/{id}/verify
GET  /v1/domains/{id}/breaches
GET  /v1/domains/{id}/breached-emails
```

### Admin (cookie session + TOTP)
```
GET  /v1/admin/users
POST /v1/admin/breaches              # add local-only breach
POST /v1/admin/breaches/{id}/retire
GET  /v1/admin/api-keys
POST /v1/admin/api-keys/{id}/revoke
GET  /v1/admin/audit
PATCH /v1/admin/branding
```

### Pwned Passwords (Cloudflare Worker)
```
GET  /api/passwords/range/{5-hex}              # SHA-1
GET  /api/passwords/range/{5-hex}?mode=ntlm    # NTLM
```

---

## 8. Security & privacy

1. **Passwords** never leave the browser. SHA-1 is computed client-side
   with WebCrypto; only the 5-char prefix is sent.
2. **Emails** for the lookup form may go server-side (with the user's
   visible consent on the form) but we hash and discard them after
   request handling. Subscriber-list emails are stored hashed
   (`sha256(lower(email))`); the plaintext column is encrypted at rest
   via PostgreSQL TDE / pgcrypto and used only for sending.
3. **Turnstile** on every public form to throttle abuse.
4. **Rate limits** per IP and per API key, sliding-window via Redis.
5. **CORS:** the API only allows our own origins; the Worker allows
   `*` so third-party password checkers can use it.
6. **CSP:** strict, with `'self'` plus Cloudflare and Stripe.
7. **Cookies:** all `Secure; HttpOnly; SameSite=Lax`; consent banner
   meets GDPR-style opt-in for analytics.
8. **Audit log** for every admin action and every breach-data write.
9. **Privacy policy** and **cookie policy** published in all three
   locales. Sources tracked in `packages/i18n-data`.
10. **Local law:** the Uzbek "Shaxsga doir ma'lumotlar" law expects
    Uzbek-citizen personal data to be processed on servers located in
    the Republic of Uzbekistan; production deployment region is left
    open in this v1 doc until hosting is decided, but the schema is
    ready to support a UZ-hosted Postgres.
11. **k-anonymity** is the default for both the password and the
    optional account-range path.

---

## 9. Localisation of every public surface

| Surface                              | uz | ru | en |
|--------------------------------------|----|----|----|
| Web pages (routes, copy, errors)     | ✅ | ✅ | ✅ |
| Email templates (confirm, breach)    | ✅ | ✅ | ✅ |
| API error bodies (`detail`, `title`) | ✅ | ✅ | ✅ |
| Privacy & Cookie policy              | ✅ | ✅ | ✅ |
| Sitemap (`hreflang` per URL)         | ✅ | ✅ | ✅ |
| Stripe checkout (locale param)       | ✅ | ✅ | ✅ |

---

## 10. Testing strategy

- **Unit:** `pytest` for `apps/api`; `vitest` for `apps/web` and
  `apps/worker`.
- **Integration:** `pytest` against a Postgres + Redis spun up by the
  same `infra/docker-compose.yml` used for local dev.
- **E2E:** `playwright` test suite that exercises:
  1. Email lookup happy path (uz, ru, en).
  2. Password lookup with k-anonymity (uz, ru, en).
  3. Notification subscribe + confirm.
  4. Domain DNS verification (mocked DNS).
  5. API-key creation + Stripe checkout (test mode).
- **Load:** `k6` script for `/v1/breaches/account` and the password
  range endpoint, gated to the `load` job in CI on demand.
- **Translation drift:** a CI step fails if any key exists in `en`
  but not in `uz` or `ru`.

---

## 11. CI / CD

- GitHub Actions workflow `.github/workflows/ci.yml`:
  1. `setup` (pnpm + uv).
  2. `lint` — `pnpm -r lint`, `uv run ruff check`,
     `uv run ruff format --check`.
  3. `typecheck` — `pnpm -r typecheck`, `uv run mypy`.
  4. `test` — `pnpm -r test --run`, `uv run pytest`.
  5. `build` — `pnpm -r build`, `uv build`, `wrangler deploy --dry-run`.
- Branching: `main` is protected. PRs must pass CI. No direct pushes.
- Releases: image tags `web:<sha>`, `api:<sha>` pushed to GHCR; worker
  deployed via `wrangler` on tag.

---

## 12. Phased rollout

| Phase | Scope                                                      |
|-------|------------------------------------------------------------|
| 0     | Repo skeleton, ARCHITECTURE.md, CI green                   |
| 1     | Web shell + i18n + Privacy/Cookie/Security pages           |
| 2     | Pwned Passwords worker + frontend lookup page              |
| 3     | API: `breaches/account` + HIBP proxy + Redis cache         |
| 4     | Notifications (subscribe + double opt-in + daily job)      |
| 5     | Domain search + DNS / email / meta verification            |
| 6     | Public API + magic-link auth + Stripe checkout             |
| 7     | Admin panel + branding + audit log                         |
| 8     | Hardening: WAF rules, runbooks, monitoring, load tests     |

This document is the source of truth. Any deviation in code must come
with an updated section here in the same PR.
