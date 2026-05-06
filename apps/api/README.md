# Xavfsizmi API

FastAPI backend for the Xavfsizmi project. Provides:

- HIBP API proxy (email breach search, paste search, domain search) with
  Redis caching and per-IP rate limiting.
- Notification subscription service with double opt-in (SMTP).
- Domain ownership verification (DNS TXT, email, meta tag).
- Public API: API-key issuance, tiered rate limits, Stripe billing.
- Admin endpoints: branding, breach curation, audit log.

## Layout

```
src/xavfsizmi_api/
  main.py                FastAPI app factory + lifespan
  config.py              Pydantic settings (env)
  core/
    db.py                AsyncEngine, session factory
    redis.py             Redis client
    i18n.py              Locale negotiation, Accept-Language parser
    ratelimit.py         Token bucket via Redis
    turnstile.py         Cloudflare Turnstile verify
    auth.py              Magic-link sessions + API-key auth
    errors.py            RFC 7807 problem+json
  routers/
    breaches.py
    pastes.py
    domains.py
    notifications.py
    api_keys.py
    admin.py
    health.py
  services/
    hibp_client.py       httpx wrapper around HIBP v3
    breach_service.py
    domain_service.py
    notification_service.py
    email_service.py
    stripe_service.py
  models/                SQLAlchemy ORM
  schemas/               Pydantic request/response DTOs
  translations/          Catalogues for emails + API errors
tests/                   pytest suite
```

## Local dev

```bash
uv sync
cp .env.example .env
docker compose -f ../../infra/docker-compose.yml up -d   # Postgres + Redis
uv run alembic upgrade head
uv run uvicorn xavfsizmi_api.main:app --reload --port 8000
```
