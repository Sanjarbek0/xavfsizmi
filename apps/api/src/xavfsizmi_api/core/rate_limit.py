"""Per-IP token-bucket-ish rate limiting against Redis.

Key shape: ``rl:{scope}:{ip}:{minute_bucket}`` with a 60s TTL — coarse but enough
for the public lookup endpoints. API-key tiers (free/pro/high_rpm) use the same
helper with a different scope key.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import redis.asyncio as redis
from fastapi import Request

from .errors import ProblemError


@dataclass(slots=True)
class RateLimit:
    scope: str
    limit_per_minute: int


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    if request.client is not None:
        return request.client.host
    return "unknown"


async def enforce(client: redis.Redis, request: Request, rl: RateLimit) -> int:
    """Increment the counter for this IP+scope; raise 429 on overflow.

    Returns the (post-increment) count so callers can surface it as a header.
    """
    bucket = int(time.time() // 60)
    key = f"rl:{rl.scope}:{client_ip(request)}:{bucket}"
    pipe = client.pipeline(transaction=False)
    pipe.incr(key)
    pipe.expire(key, 65)
    count, _ = await pipe.execute()
    current = int(count)
    if current > rl.limit_per_minute:
        raise ProblemError(
            status=429,
            type_="https://xavfsizmi.example/errors/rate_limited",
            title_key="rate_limited.title",
            detail_key="rate_limited.detail",
        )
    return current
