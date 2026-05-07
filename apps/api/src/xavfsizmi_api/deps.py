"""Reusable FastAPI dependencies."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

import redis.asyncio as redis
from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import Settings, get_settings
from .core.errors import ProblemError
from .db.models import ApiKey, User
from .db.session import get_session
from .services.api_keys import authenticate_key
from .services.auth import SESSION_COOKIE_NAME, read_session_cookie
from .services.cache import get_redis
from .services.domains import DefaultDomainVerifier, DomainVerifier
from .services.email import EmailSender, get_email_sender
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


def email_sender_dep() -> EmailSender:
    return get_email_sender()


def domain_verifier_dep() -> DomainVerifier:
    return DefaultDomainVerifier()


HIBPDep = Annotated[HIBPClient, Depends(hibp_client_dep)]
TurnstileDep = Annotated[TurnstileVerifier, Depends(turnstile_dep)]
RedisDep = Annotated[redis.Redis, Depends(redis_dep)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
EmailDep = Annotated[EmailSender, Depends(email_sender_dep)]
DomainVerifierDep = Annotated[DomainVerifier, Depends(domain_verifier_dep)]


async def current_user(
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
) -> User:
    """Resolve the user from the signed session cookie. Raises 401 otherwise."""
    cookie = request.cookies.get(SESSION_COOKIE_NAME)
    user_id = read_session_cookie(cookie, settings=settings)
    if user_id is None:
        raise ProblemError(
            status=401,
            title_key="auth.unauthorized.title",
            detail_key="auth.unauthorized.detail",
        )
    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None or user.is_blocked:
        raise ProblemError(
            status=401,
            title_key="auth.unauthorized.title",
            detail_key="auth.unauthorized.detail",
        )
    return user


CurrentUserDep = Annotated[User, Depends(current_user)]


async def authenticated_api_key(
    request: Request,
    session: SessionDep,
) -> ApiKey:
    """Resolve a request's `X-API-Key` header and verify the hash."""
    plaintext = request.headers.get("x-api-key") or request.headers.get("authorization")
    if plaintext and plaintext.lower().startswith("bearer "):
        plaintext = plaintext.split(" ", 1)[1]
    if not plaintext:
        raise ProblemError(
            status=401,
            title_key="auth.api_key.missing.title",
            detail_key="auth.api_key.missing.detail",
        )
    record = await authenticate_key(session, plaintext=plaintext)
    if record is None:
        raise ProblemError(
            status=401,
            title_key="auth.api_key.invalid.title",
            detail_key="auth.api_key.invalid.detail",
        )
    return record


ApiKeyDep = Annotated[ApiKey, Depends(authenticated_api_key)]
