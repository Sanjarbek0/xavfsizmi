"""Shared pytest fixtures.

These provide an in-memory fake Redis and dependency overrides that swap the
HIBPClient + TurnstileVerifier with controllable doubles so router tests don't
need network or a live Redis.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from xavfsizmi_api.deps import hibp_client_dep, redis_dep, turnstile_dep
from xavfsizmi_api.main import app as real_app


class FakeRedis:
    """Tiny subset of `redis.asyncio.Redis` that lives entirely in memory.

    Implements only the operations the API actually calls: ``get``, ``set``
    (with ``ex`` TTL semantics), and ``pipeline().incr().expire().execute()``.
    """

    def __init__(self) -> None:
        self._store: dict[str, tuple[str | int, float | None]] = {}

    def _expired(self, key: str) -> bool:
        item = self._store.get(key)
        if item is None:
            return True
        _, deadline = item
        if deadline is not None and deadline <= time.time():
            self._store.pop(key, None)
            return True
        return False

    async def get(self, key: str) -> str | None:
        if self._expired(key):
            return None
        value = self._store[key][0]
        return str(value) if not isinstance(value, str) else value

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        deadline = time.time() + ex if ex is not None else None
        self._store[key] = (value, deadline)

    def pipeline(self, transaction: bool = False) -> FakePipeline:
        return FakePipeline(self)

    async def aclose(self) -> None:  # pragma: no cover - cleanup hook
        self._store.clear()

    def reset(self) -> None:
        self._store.clear()


class FakePipeline:
    def __init__(self, parent: FakeRedis) -> None:
        self._parent = parent
        self._ops: list[tuple[str, tuple[Any, ...]]] = []

    def incr(self, key: str) -> FakePipeline:
        self._ops.append(("incr", (key,)))
        return self

    def expire(self, key: str, seconds: int) -> FakePipeline:
        self._ops.append(("expire", (key, seconds)))
        return self

    async def execute(self) -> list[Any]:
        results: list[Any] = []
        for name, args in self._ops:
            if name == "incr":
                key = args[0]
                current = 0
                if not self._parent._expired(key):
                    raw = self._parent._store[key][0]
                    current = int(raw) if not isinstance(raw, int) else raw
                current += 1
                old_deadline = self._parent._store[key][1] if key in self._parent._store else None
                self._parent._store[key] = (current, old_deadline)
                results.append(current)
            elif name == "expire":
                key, seconds = args
                if key in self._parent._store:
                    value, _ = self._parent._store[key]
                    self._parent._store[key] = (value, time.time() + seconds)
                results.append(True)
        self._ops.clear()
        return results


class FakeHIBP:
    def __init__(self) -> None:
        self.breached_payload: list[dict[str, Any]] = []
        self.all_breaches_payload: list[dict[str, Any]] = []
        self.breach_payload: dict[str, dict[str, Any]] = {}
        self.pastes_payload: list[dict[str, Any]] = []
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def aclose(self) -> None:
        pass

    async def breached_account(
        self,
        email: str,
        *,
        truncate_response: bool = False,
        include_unverified: bool = True,
    ) -> list[dict[str, Any]]:
        self.calls.append(
            (
                "breached_account",
                {
                    "email": email,
                    "truncate_response": truncate_response,
                    "include_unverified": include_unverified,
                },
            )
        )
        return list(self.breached_payload)

    async def all_breaches(self, *, domain: str | None = None) -> list[dict[str, Any]]:
        self.calls.append(("all_breaches", {"domain": domain}))
        return list(self.all_breaches_payload)

    async def breach(self, name: str) -> dict[str, Any] | None:
        self.calls.append(("breach", {"name": name}))
        return self.breach_payload.get(name)

    async def pastes(self, email: str) -> list[dict[str, Any]]:
        self.calls.append(("pastes", {"email": email}))
        return list(self.pastes_payload)


class FakeTurnstile:
    def __init__(self, ok: bool = True) -> None:
        self.ok = ok

    async def verify(self, token: str | None, *, remote_ip: str | None = None) -> bool:
        return self.ok


@pytest.fixture
def fake_redis() -> FakeRedis:
    return FakeRedis()


@pytest.fixture
def fake_hibp() -> FakeHIBP:
    return FakeHIBP()


@pytest.fixture
def fake_turnstile() -> FakeTurnstile:
    return FakeTurnstile()


@pytest.fixture
def app(
    fake_redis: FakeRedis,
    fake_hibp: FakeHIBP,
    fake_turnstile: FakeTurnstile,
) -> Iterator[FastAPI]:
    async def _hibp_override() -> Any:
        yield fake_hibp

    real_app.dependency_overrides[redis_dep] = lambda: fake_redis
    real_app.dependency_overrides[hibp_client_dep] = _hibp_override
    real_app.dependency_overrides[turnstile_dep] = lambda: fake_turnstile
    try:
        yield real_app
    finally:
        real_app.dependency_overrides.pop(redis_dep, None)
        real_app.dependency_overrides.pop(hibp_client_dep, None)
        real_app.dependency_overrides.pop(turnstile_dep, None)


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)
