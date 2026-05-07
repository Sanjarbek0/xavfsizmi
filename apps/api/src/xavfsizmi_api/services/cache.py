"""Async Redis client + tiny JSON cache helpers.

Centralised so every caller hits one connection pool and so tests can swap the
client implementation in/out via dependency overrides.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

import redis.asyncio as redis

from ..config import get_settings


@lru_cache(maxsize=1)
def get_redis() -> redis.Redis:
    settings = get_settings()
    return redis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
    )


async def cache_get_json(client: redis.Redis, key: str) -> Any | None:
    raw = await client.get(key)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


async def cache_set_json(client: redis.Redis, key: str, value: Any, ttl_seconds: int) -> None:
    await client.set(key, json.dumps(value, separators=(",", ":")), ex=ttl_seconds)
