"""Reusable FastAPI dependencies."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

import redis.asyncio as redis
from fastapi import Depends

from .config import Settings, get_settings
from .services.cache import get_redis
from .services.hibp_client import HIBPClient
from .services.turnstile import TurnstileVerifier


async def hibp_client_dep(
    settings: Annotated[Settings, Depends(get_settings)],
) -> AsyncIterator[HIBPClient]:
    client = HIBPClient(settings)
    try:
        yield client
    finally:
        await client.aclose()


def turnstile_dep(
    settings: Annotated[Settings, Depends(get_settings)],
) -> TurnstileVerifier:
    return TurnstileVerifier(settings)


def redis_dep() -> redis.Redis:
    return get_redis()


HIBPDep = Annotated[HIBPClient, Depends(hibp_client_dep)]
TurnstileDep = Annotated[TurnstileVerifier, Depends(turnstile_dep)]
RedisDep = Annotated[redis.Redis, Depends(redis_dep)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
