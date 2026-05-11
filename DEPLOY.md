# Deploying Xavfsizmi

This document describes three ways to deploy Xavfsizmi to a real production
environment. Pick the option that matches your operations model.

| Option | Best for | Cost (approx.) |
| --- | --- | --- |
| [Hetzner / single VM](#1-single-vm-hetzner--digitalocean) | One operator, full control, lowest cost | $5–20 / month |
| [Fly.io](#2-flyio) | No-ops Postgres + Redis, multi-region | $10–40 / month |
| [Render](#3-render) | Managed dashboard, automatic deploys from main | $14–50 / month |

All three options pair with Cloudflare for:

* `passwords.xavfsizmi.example` — the **Cloudflare Worker** that serves
  k-anonymity password range lookups out of an R2 bucket.
  See [`infra/seed-pwned-passwords.md`](infra/seed-pwned-passwords.md) for the
  one-time R2 import.
* (Optional) Cloudflare in front of the web hostname for caching + Turnstile.

## Pre-flight checklist (any option)

1. Buy your domain (e.g. `xavfsizmi.example`) and put DNS at Cloudflare.
2. Decide hostnames:
   * `xavfsizmi.example`           – web SPA
   * `api.xavfsizmi.example`       – FastAPI backend
   * `passwords.xavfsizmi.example` – Pwned Passwords Worker
3. Buy / create accounts for:
   * **Cloudflare** (free plan is enough).
   * **HIBP API key** — https://haveibeenpwned.com/API/Key
   * **SMTP provider** — Amazon SES, Mailgun, Postmark, or Resend.
   * **Stripe** (only if you want billing) — create products for the
     `Pro` and `High RPM` tiers; copy the price IDs into `STRIPE_PRICE_*`.
   * **Turnstile** (optional) — https://dash.cloudflare.com/?to=/:account/turnstile

## 1. Single VM (Hetzner / DigitalOcean)

This is the cheapest reproducible setup: one Docker host running Postgres,
Redis, the API, the web SPA, and Caddy as the TLS terminator.

### 1.1 Provision

1. Create an **Ubuntu 24.04** VM (Hetzner CX22 / DO `s-1vcpu-2gb` is enough
   for low traffic).
2. Point DNS A records for `xavfsizmi.example` and `api.xavfsizmi.example`
   to the VM's IPv4 address.
3. SSH in and install Docker:

   ```bash
   ssh root@<VM_IP>
   apt-get update && apt-get install -y ca-certificates curl git
   install -m 0755 -d /etc/apt/keyrings
   curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
   chmod a+r /etc/apt/keyrings/docker.asc
   echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
       | tee /etc/apt/sources.list.d/docker.list
   apt-get update
   apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
   ```

### 1.2 Clone + configure

```bash
git clone https://github.com/Sanjarbek0/xavfsizmi.git /opt/xavfsizmi
cd /opt/xavfsizmi
cp infra/.env.prod.example infra/.env.prod
$EDITOR infra/.env.prod                # fill in every "changeme" value
```

Generate a strong session secret:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(64))"
```

### 1.3 Bring the stack up

```bash
docker compose --env-file infra/.env.prod -f infra/docker-compose.prod.yml up -d --build
docker compose --env-file infra/.env.prod -f infra/docker-compose.prod.yml ps
```

The API container runs Alembic migrations on startup. Tail logs:

```bash
docker compose --env-file infra/.env.prod -f infra/docker-compose.prod.yml logs -f api
```

Caddy will print `certificate obtained` lines for each hostname the first
time it sees traffic. Visit:

* `https://xavfsizmi.example/` — SPA.
* `https://api.xavfsizmi.example/healthz` — should return `{"status":"ok"}`.
* `https://api.xavfsizmi.example/readyz` — pings DB + Redis.

### 1.4 Updates

```bash
cd /opt/xavfsizmi
git pull
docker compose --env-file infra/.env.prod -f infra/docker-compose.prod.yml up -d --build api web
```

Backups: snapshot the `postgres-data` volume daily. For Hetzner, enable the
automated snapshot service on the VM.

## 2. Fly.io

Fly gives you managed Postgres + edge deploys without leaving the CLI.

### 2.1 Install + sign in

```bash
curl -L https://fly.io/install.sh | sh
fly auth login
```

### 2.2 Provision Postgres + Redis (Upstash)

```bash
fly postgres create --name xavfsizmi-pg --region fra
# Copy the connection URL it prints; you'll need it below.

fly redis create --name xavfsizmi-redis --region fra
# Or use Upstash Redis: https://fly.io/docs/reference/redis/
```

### 2.3 Deploy the API

Create `fly.api.toml` from the example below (committing it is fine — secrets
go in `fly secrets`):

```toml
app = "xavfsizmi-api"
primary_region = "fra"

[build]
  dockerfile = "infra/Dockerfile.api"

[http_service]
  internal_port = 8000
  force_https = true
  auto_stop_machines = false
  auto_start_machines = true
  min_machines_running = 1

[[http_service.checks]]
  interval = "30s"
  timeout = "5s"
  method = "GET"
  path = "/healthz"
```

Set secrets and deploy:

```bash
fly apps create xavfsizmi-api
fly secrets set --app xavfsizmi-api \
    DATABASE_URL='postgresql+asyncpg://...' \
    REDIS_URL='redis://...' \
    HIBP_API_KEY='...' \
    SESSION_SECRET="$(python3 -c 'import secrets;print(secrets.token_urlsafe(64))')" \
    ALLOWED_ORIGINS='https://xavfsizmi.example' \
    SMTP_HOST='email-smtp.eu-central-1.amazonaws.com' \
    SMTP_PORT='587' \
    SMTP_USERNAME='...' \
    SMTP_PASSWORD='...' \
    SMTP_FROM='Xavfsizmi <noreply@xavfsizmi.example>' \
    SMTP_TLS='true' \
    ADMIN_EMAILS='you@xavfsizmi.example'

fly deploy --config fly.api.toml --dockerfile infra/Dockerfile.api
```

### 2.4 Deploy the web SPA

Vite bakes env vars at build time, so pass them as build args:

```toml
# fly.web.toml
app = "xavfsizmi-web"
primary_region = "fra"

[build]
  dockerfile = "infra/Dockerfile.web"
  [build.args]
    VITE_API_BASE_URL = "https://api.xavfsizmi.example"
    VITE_PASSWORDS_BASE_URL = "https://passwords.xavfsizmi.example"
    VITE_BRAND_NAME = "Xavfsizmi"

[http_service]
  internal_port = 8080
  force_https = true
```

```bash
fly apps create xavfsizmi-web
fly deploy --config fly.web.toml --dockerfile infra/Dockerfile.web
```

Map your custom domain to each app:

```bash
fly certs create --app xavfsizmi-web xavfsizmi.example
fly certs create --app xavfsizmi-api api.xavfsizmi.example
```

## 3. Render

Render auto-deploys from GitHub on push. Use the `Blueprint` workflow:

1. Push the repo to GitHub (already done).
2. In Render's dashboard click **New → Blueprint** and point it at this repo.
   Render reads `render.yaml` (see below) and creates everything.

A starter `render.yaml`:

```yaml
services:
  - type: web
    name: xavfsizmi-api
    runtime: docker
    dockerfilePath: ./infra/Dockerfile.api
    healthCheckPath: /healthz
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: xavfsizmi-pg
          property: connectionString
      - key: REDIS_URL
        fromService:
          name: xavfsizmi-redis
          type: redis
          property: connectionString
      - key: HIBP_API_KEY
        sync: false   # set in dashboard
      - key: SESSION_SECRET
        generateValue: true
      - key: ALLOWED_ORIGINS
        value: https://xavfsizmi.example

  - type: web
    name: xavfsizmi-web
    runtime: docker
    dockerfilePath: ./infra/Dockerfile.web
    dockerBuildArgs:
      VITE_API_BASE_URL: https://api.xavfsizmi.example
      VITE_PASSWORDS_BASE_URL: https://passwords.xavfsizmi.example
      VITE_BRAND_NAME: Xavfsizmi

  - type: redis
    name: xavfsizmi-redis
    ipAllowList: []

databases:
  - name: xavfsizmi-pg
    plan: starter
```

Render will provision Postgres, Redis, build both Docker images, and ship them
behind their managed TLS proxy. Add custom domains in the dashboard.

## 4. Deploying the Cloudflare Worker

```bash
cd apps/worker
pnpm install --frozen-lockfile

# Auth once (opens browser):
pnpm exec wrangler login

# Deploy preview to *.workers.dev:
pnpm exec wrangler deploy

# Deploy to the production route (after editing the [env.production] block
# in apps/worker/wrangler.toml with your real route + zone):
pnpm exec wrangler deploy --env production
```

The Worker depends on the R2 bucket being seeded with the Pwned Passwords
dataset. See [`infra/seed-pwned-passwords.md`](infra/seed-pwned-passwords.md).

## 5. Operational notes

* **Database backups** — `pg_dump` nightly, off-host (S3 / Backblaze B2 / R2).
* **Log shipping** — for the single-VM setup, pipe Docker logs into Loki +
  Grafana (`docker run grafana/loki`); for Fly use `fly logs`; for Render use
  the dashboard's `Logs` tab.
* **Stripe webhook URL** — point your Stripe dashboard webhook at
  `https://api.xavfsizmi.example/v1/webhooks/stripe`. Whitelist:
  `customer.subscription.created`, `customer.subscription.updated`,
  `customer.subscription.deleted`, `checkout.session.completed`.
* **Rate limit tuning** — every limit lives in `infra/.env.prod` (`RL_*` keys).
  Raise or lower without rebuilding the image.
* **Multiple API replicas** — only one replica should run migrations on startup.
  Set `RUN_MIGRATIONS=0` on the second+ replica.
