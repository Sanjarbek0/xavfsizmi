"""API key usage telemetry.

Per-day request counters live in Redis with a 30-day TTL. They are also flushed
into the durable ``api_key_usage`` table on each increment so the admin panel
and per-user dashboards can show historical totals without depending on Redis.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import redis.asyncio as redis
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import ApiKeyUsage

USAGE_TTL_SECONDS = 60 * 60 * 24 * 35  # keep a little more than a month


def _today_utc() -> date:
    return datetime.now(UTC).date()


def _redis_key(api_key_id: uuid.UUID, day: date) -> str:
    return f"usage:{api_key_id}:{day.isoformat()}"


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _day_start_utc(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


async def record_call(
    redis_client: redis.Redis, session: AsyncSession, *, api_key_id: uuid.UUID
) -> int:
    """Increment today's counter for ``api_key_id``. Returns the new value."""
    today = _today_utc()
    key = _redis_key(api_key_id, today)
    pipe = redis_client.pipeline()
    pipe.incr(key)
    pipe.expire(key, USAGE_TTL_SECONDS)
    results = await pipe.execute()
    new_value = int(results[0])

    day_dt = _day_start_utc(today)
    rows = (
        await session.execute(select(ApiKeyUsage).where(ApiKeyUsage.api_key_id == api_key_id))
    ).scalars()
    existing: ApiKeyUsage | None = None
    for row in rows:
        if _as_utc(row.day).date() == today:
            existing = row
            break
    if existing is None:
        session.add(ApiKeyUsage(api_key_id=api_key_id, day=day_dt, request_count=new_value))
    else:
        existing.request_count = new_value
    return new_value


@dataclass(slots=True)
class DailyUsage:
    day: date
    request_count: int


async def today_count(redis_client: redis.Redis, *, api_key_id: uuid.UUID) -> int:
    """Read today's request count straight from Redis (no DB hit)."""
    raw = await redis_client.get(_redis_key(api_key_id, _today_utc()))
    return int(raw) if raw is not None else 0


async def current_minute(redis_client: redis.Redis, *, tier: str, ip: str) -> int:
    """Peek at the current minute's rate-limit bucket (without incrementing).

    Mirrors the keying convention used by ``core.rate_limit`` so we can show a
    "remaining this minute" stat without touching the bucket. ``ip`` is reused
    here as the bucket discriminator — the public API endpoint actually keys
    by API key id (it overwrites ``request.scope['client']``), so the caller
    passes the api key id string to match that.
    """
    import time as _time

    bucket = int(_time.time() // 60)
    key = f"rl:api.tier.{tier}:{ip}:{bucket}"
    raw = await redis_client.get(key)
    return int(raw) if raw is not None else 0


async def history(
    session: AsyncSession, *, api_key_id: uuid.UUID, days: int = 30
) -> list[DailyUsage]:
    """Last ``days`` of usage rows from the durable table, newest first."""
    capped = max(1, min(days, 90))
    cutoff_day = _today_utc() - timedelta(days=capped)
    rows = (
        await session.execute(
            select(ApiKeyUsage)
            .where(ApiKeyUsage.api_key_id == api_key_id)
            .order_by(desc(ApiKeyUsage.day))
        )
    ).scalars()
    out: list[DailyUsage] = []
    for row in rows:
        d = _as_utc(row.day).date()
        if d < cutoff_day:
            continue
        out.append(DailyUsage(day=d, request_count=int(row.request_count)))
    return out


__all__ = [
    "USAGE_TTL_SECONDS",
    "DailyUsage",
    "current_minute",
    "history",
    "record_call",
    "today_count",
]
