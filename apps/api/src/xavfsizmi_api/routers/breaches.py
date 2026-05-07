"""Breach lookup endpoints (HIBP proxy with Redis cache + per-IP rate limit + Turnstile).

Endpoints:
    POST /v1/breaches/account     -> per-account breach list, Turnstile gated
    GET  /v1/breaches             -> all breaches (with optional ?domain=)
    GET  /v1/breaches/{name}      -> single breach detail
    POST /v1/breaches/paste       -> paste search for an account, Turnstile gated
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from fastapi import APIRouter, Path, Query, Request
from pydantic import BaseModel, EmailStr, Field

from ..core.errors import ProblemError
from ..core.rate_limit import RateLimit, client_ip, enforce
from ..deps import HIBPDep, RedisDep, SettingsDep, TurnstileDep
from ..services.cache import cache_get_json, cache_set_json
from ..services.hibp_client import HIBPError

router = APIRouter(prefix="/breaches", tags=["breaches"])

# Rate limits
_RL_ACCOUNT = RateLimit(scope="breach.account", limit_per_minute=5)
_RL_PASTE = RateLimit(scope="breach.paste", limit_per_minute=5)
_RL_LIST = RateLimit(scope="breach.list", limit_per_minute=60)

# TTLs (seconds)
_TTL_ACCOUNT = 900  # 15 min
_TTL_PASTE = 900  # 15 min
_TTL_ALL_BREACHES = 3600  # 1 hour
_TTL_BREACH = 6 * 3600  # 6 hours

_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$"
)


# --- request / response models -------------------------------------------------


class AccountLookupRequest(BaseModel):
    email: EmailStr
    turnstile_token: str | None = Field(default=None, alias="turnstileToken")
    truncate_response: bool = Field(default=False, alias="truncateResponse")
    include_unverified: bool = Field(default=True, alias="includeUnverified")

    model_config = {"populate_by_name": True}


class BreachSummary(BaseModel):
    name: str
    title: str | None = None
    domain: str | None = None
    breach_date: str | None = None
    pwn_count: int | None = None
    is_verified: bool | None = None
    is_sensitive: bool | None = None
    is_fabricated: bool | None = None
    is_retired: bool | None = None
    is_spam_list: bool | None = None
    description: str | None = None
    data_classes: list[str] | None = None
    logo_path: str | None = None


class AccountLookupResponse(BaseModel):
    email: str
    breaches: list[BreachSummary]
    cached: bool = False


class PasteRequest(BaseModel):
    email: EmailStr
    turnstile_token: str | None = Field(default=None, alias="turnstileToken")

    model_config = {"populate_by_name": True}


class Paste(BaseModel):
    source: str
    id: str
    title: str | None = None
    date: str | None = None
    email_count: int | None = None


class PasteResponse(BaseModel):
    email: str
    pastes: list[Paste]
    cached: bool = False


# --- helpers -------------------------------------------------------------------


def _summary(b: dict[str, Any]) -> BreachSummary:
    return BreachSummary(
        name=str(b.get("Name") or ""),
        title=b.get("Title"),
        domain=b.get("Domain"),
        breach_date=b.get("BreachDate"),
        pwn_count=b.get("PwnCount"),
        is_verified=b.get("IsVerified"),
        is_sensitive=b.get("IsSensitive"),
        is_fabricated=b.get("IsFabricated"),
        is_retired=b.get("IsRetired"),
        is_spam_list=b.get("IsSpamList"),
        description=b.get("Description"),
        data_classes=b.get("DataClasses"),
        logo_path=b.get("LogoPath"),
    )


def _paste(p: dict[str, Any]) -> Paste:
    return Paste(
        source=str(p.get("Source") or ""),
        id=str(p.get("Id") or ""),
        title=p.get("Title"),
        date=p.get("Date"),
        email_count=p.get("EmailCount"),
    )


def _account_hash(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()


def _wrap_hibp_error(exc: HIBPError) -> ProblemError:
    if exc.status == 401:
        return ProblemError(
            status=502,
            title_key="hibp.upstream_error.title",
            detail_key="hibp.upstream_error.detail",
        )
    if exc.status and 500 <= exc.status < 600:
        return ProblemError(
            status=502,
            title_key="hibp.upstream_error.title",
            detail_key="hibp.upstream_error.detail",
        )
    return ProblemError(
        status=502,
        title_key="hibp.upstream_error.title",
        detail_key="hibp.upstream_error.detail",
    )


# --- routes -------------------------------------------------------------------


@router.post("/account", response_model=AccountLookupResponse)
async def lookup_account(
    payload: AccountLookupRequest,
    request: Request,
    hibp: HIBPDep,
    turnstile: TurnstileDep,
    redis_client: RedisDep,
    settings: SettingsDep,
) -> AccountLookupResponse:
    await enforce(redis_client, request, _RL_ACCOUNT)

    if settings.turnstile_secret_key:
        ok = await turnstile.verify(payload.turnstile_token, remote_ip=client_ip(request))
        if not ok:
            raise ProblemError(
                status=403,
                title_key="turnstile.failed.title",
                detail_key="turnstile.failed.detail",
            )

    email = str(payload.email).lower()
    cache_key = (
        f"hibp:account:{_account_hash(email)}"
        f":t={int(payload.truncate_response)}:u={int(payload.include_unverified)}"
    )

    cached = await cache_get_json(redis_client, cache_key)
    if isinstance(cached, list):
        return AccountLookupResponse(
            email=email,
            breaches=[_summary(b) for b in cached],
            cached=True,
        )

    try:
        breaches = await hibp.breached_account(
            email,
            truncate_response=payload.truncate_response,
            include_unverified=payload.include_unverified,
        )
    except HIBPError as e:
        raise _wrap_hibp_error(e) from e

    await cache_set_json(redis_client, cache_key, breaches, _TTL_ACCOUNT)
    return AccountLookupResponse(
        email=email,
        breaches=[_summary(b) for b in breaches],
        cached=False,
    )


@router.get("", response_model=list[BreachSummary])
async def list_breaches(
    request: Request,
    hibp: HIBPDep,
    redis_client: RedisDep,
    domain: str | None = Query(default=None, max_length=253),
) -> list[BreachSummary]:
    await enforce(redis_client, request, _RL_LIST)

    if domain is not None:
        domain = domain.lower().strip()
        if not _DOMAIN_RE.match(domain):
            raise ProblemError(status=400, detail_key="validation.bad_email.detail")

    cache_key = f"hibp:all_breaches:{domain or '*'}"
    cached = await cache_get_json(redis_client, cache_key)
    if isinstance(cached, list):
        return [_summary(b) for b in cached]

    try:
        breaches = await hibp.all_breaches(domain=domain)
    except HIBPError as e:
        raise _wrap_hibp_error(e) from e

    await cache_set_json(redis_client, cache_key, breaches, _TTL_ALL_BREACHES)
    return [_summary(b) for b in breaches]


@router.get("/{name}", response_model=BreachSummary)
async def get_breach(
    request: Request,
    hibp: HIBPDep,
    redis_client: RedisDep,
    name: str = Path(..., min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._-]+$"),
) -> BreachSummary:
    await enforce(redis_client, request, _RL_LIST)

    cache_key = f"hibp:breach:{name.lower()}"
    cached = await cache_get_json(redis_client, cache_key)
    if isinstance(cached, dict):
        return _summary(cached)

    try:
        breach = await hibp.breach(name)
    except HIBPError as e:
        raise _wrap_hibp_error(e) from e

    if breach is None:
        raise ProblemError(status=404, title_key="breach.not_found.title")

    await cache_set_json(redis_client, cache_key, breach, _TTL_BREACH)
    return _summary(breach)


@router.post("/paste", response_model=PasteResponse)
async def lookup_pastes(
    payload: PasteRequest,
    request: Request,
    hibp: HIBPDep,
    turnstile: TurnstileDep,
    redis_client: RedisDep,
    settings: SettingsDep,
) -> PasteResponse:
    await enforce(redis_client, request, _RL_PASTE)

    if settings.turnstile_secret_key:
        ok = await turnstile.verify(payload.turnstile_token, remote_ip=client_ip(request))
        if not ok:
            raise ProblemError(
                status=403,
                title_key="turnstile.failed.title",
                detail_key="turnstile.failed.detail",
            )

    email = str(payload.email).lower()
    cache_key = f"hibp:paste:{_account_hash(email)}"

    cached = await cache_get_json(redis_client, cache_key)
    if isinstance(cached, list):
        return PasteResponse(email=email, pastes=[_paste(p) for p in cached], cached=True)

    try:
        pastes = await hibp.pastes(email)
    except HIBPError as e:
        raise _wrap_hibp_error(e) from e

    await cache_set_json(redis_client, cache_key, pastes, _TTL_PASTE)
    return PasteResponse(email=email, pastes=[_paste(p) for p in pastes], cached=False)
