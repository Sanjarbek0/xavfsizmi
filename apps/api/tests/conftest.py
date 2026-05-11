"""Shared pytest fixtures.

These provide an in-memory fake Redis, an in-memory fake email sender, an
in-memory fake domain verifier, and a real-but-isolated SQLite-backed async
session so router tests can hit the DB without Postgres.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from xavfsizmi_api.db.base import Base
from xavfsizmi_api.db.session import get_session
from xavfsizmi_api.deps import (
    billing_dep,
    domain_verifier_dep,
    email_sender_dep,
    hibp_client_dep,
    redis_dep,
    turnstile_dep,
)
from xavfsizmi_api.main import app as real_app
from xavfsizmi_api.services.billing import FakeBilling
from xavfsizmi_api.services.domains import VerificationResult
from xavfsizmi_api.services.email import EmailMessageSpec, InMemoryEmailSender


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

    async def ping(self) -> bool:
        return True

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


class FakeDomainVerifier:
    """Domain verifier that returns whatever the test wires up."""

    def __init__(self) -> None:
        self.dns_results: dict[str, VerificationResult] = {}
        self.meta_results: dict[str, VerificationResult] = {}
        self.calls: list[tuple[str, str, str]] = []

    async def verify_dns_txt(self, *, domain: str, token: str) -> VerificationResult:
        self.calls.append(("dns_txt", domain, token))
        return self.dns_results.get(domain, VerificationResult(False, "no fixture"))

    async def verify_meta_tag(self, *, domain: str, token: str) -> VerificationResult:
        self.calls.append(("meta_tag", domain, token))
        return self.meta_results.get(domain, VerificationResult(False, "no fixture"))


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
def fake_email() -> InMemoryEmailSender:
    return InMemoryEmailSender()


@pytest.fixture
def fake_verifier() -> FakeDomainVerifier:
    return FakeDomainVerifier()


@pytest.fixture
def fake_billing() -> FakeBilling:
    return FakeBilling()


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """One isolated in-memory SQLite engine per test (with cross-dialect models)."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    session = sessionmaker()
    try:
        yield session
    finally:
        await session.close()
        await engine.dispose()


@pytest.fixture
def app(
    fake_redis: FakeRedis,
    fake_hibp: FakeHIBP,
    fake_turnstile: FakeTurnstile,
    fake_email: InMemoryEmailSender,
    fake_verifier: FakeDomainVerifier,
    fake_billing: FakeBilling,
    db_session: AsyncSession,
) -> Iterator[FastAPI]:
    async def _hibp_override() -> Any:
        yield fake_hibp

    async def _session_override() -> AsyncIterator[AsyncSession]:
        # Re-use the shared in-memory session so each request sees the same data.
        try:
            yield db_session
            await db_session.commit()
        except Exception:
            await db_session.rollback()
            raise

    real_app.dependency_overrides[redis_dep] = lambda: fake_redis
    real_app.dependency_overrides[hibp_client_dep] = _hibp_override
    real_app.dependency_overrides[turnstile_dep] = lambda: fake_turnstile
    real_app.dependency_overrides[email_sender_dep] = lambda: fake_email
    real_app.dependency_overrides[domain_verifier_dep] = lambda: fake_verifier
    real_app.dependency_overrides[billing_dep] = lambda: fake_billing
    real_app.dependency_overrides[get_session] = _session_override
    try:
        yield real_app
    finally:
        for dep in (
            redis_dep,
            hibp_client_dep,
            turnstile_dep,
            email_sender_dep,
            domain_verifier_dep,
            billing_dep,
            get_session,
        ):
            real_app.dependency_overrides.pop(dep, None)


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


async def promote_user(session: AsyncSession, *, email: str, tier: str) -> None:
    """Test helper — directly bump a user's ``subscription_tier`` in the DB.

    Bypasses the Stripe webhook so individual tests can exercise tier-gated
    endpoints (e.g. creating a ``pro`` API key) without standing up a full
    billing fixture.
    """
    from sqlalchemy import select as _select

    from xavfsizmi_api.db.models import User as _User
    from xavfsizmi_api.services.api_keys import set_all_keys_tier as _set_all_keys_tier

    user = (await session.execute(_select(_User).where(_User.email == email))).scalar_one()
    user.subscription_tier = tier
    user.subscription_status = "active"
    await _set_all_keys_tier(session, user_id=user.id, tier=tier)
    await session.commit()


__all__ = [
    "EmailMessageSpec",
    "FakeBilling",
    "FakeDomainVerifier",
    "FakeHIBP",
    "FakeRedis",
    "FakeTurnstile",
    "InMemoryEmailSender",
    "VerificationResult",
    "promote_user",
]
