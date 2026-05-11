# Xavfsizmi

A multilingual breach-lookup service inspired by Have I Been Pwned, with
Uzbek (Latin), Russian and English UIs.

## What's in this monorepo

* `apps/web`      — React + Vite SPA, locale-prefixed routing, i18next.
* `apps/api`      — FastAPI backend (Python 3.12 + uv), PostgreSQL + Redis.
* `apps/worker`   — Cloudflare Worker serving Pwned Passwords k-anonymity
                    lookups from an R2 bucket.
* `packages/i18n-data`     — Shared uz/ru/en translation catalogues.
* `packages/shared-types`  — TypeScript types shared between SPA and worker.
* `packages/eslint-config` — Shared ESLint config.
* `infra/`        — Dockerfiles, docker-compose stacks, Caddyfile, nginx.conf,
                    Pwned Passwords R2 seeding guide.

## Quick links

* [`ARCHITECTURE.md`](ARCHITECTURE.md) — system design + rollout plan.
* [`DEPLOY.md`](DEPLOY.md) — production deployment guide (Hetzner / Fly.io /
  Render + Cloudflare Worker).
* [`infra/seed-pwned-passwords.md`](infra/seed-pwned-passwords.md) — how to
  populate the R2 bucket that backs `passwords.*`.

## Local development

```bash
# 1. Boot Postgres, Redis, MailHog
docker compose -f infra/docker-compose.yml up -d

# 2. API
cd apps/api
cp .env.example .env
uv sync
uv run alembic upgrade head
uv run uvicorn xavfsizmi_api.main:app --reload

# 3. Web (new terminal, from repo root)
pnpm install
pnpm --filter @xavfsizmi/web dev
```

The SPA runs on `http://localhost:5173`, the API on `http://localhost:8000`,
and MailHog (outgoing-email inspector) on `http://localhost:8025`.

## Tests

```bash
# API
cd apps/api && uv run pytest -q

# Web + worker + packages
pnpm -r lint && pnpm -r typecheck && pnpm -r test && pnpm -r build

# i18n catalogues
pnpm --filter @xavfsizmi/i18n-data run check
```

CI runs all of the above on every PR; see `.github/workflows/ci.yml`.
