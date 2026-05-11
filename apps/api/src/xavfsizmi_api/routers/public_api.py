"""Public, API-key-authenticated breach lookup endpoint.

Mirrors HIBP's `/breachedaccount/{account}` semantics: authentication via
``X-API-Key``, tier-based per-key rate limit, and the same JSON shape as the
cookie-authenticated UI endpoint. We rely on the existing HIBP proxy + Redis
cache so a key call is a few-millisecond hit if the account is hot.
"""

from __future__ import annotations

import hashlib
from typing import Any

from fastapi import APIRouter, Path, Query, Request, Response

from ..core.errors import ProblemError
from ..core.rate_limit import RateLimit, enforce
from ..deps import ApiKeyDep, HIBPDep, RedisDep, SessionDep, SettingsDep
from ..services.cache import cache_get_json, cache_set_json
from ..services.hibp_client import HIBPError
from ..services.usage import record_call
from .breaches import AccountLookupResponse, BreachSummary

router = APIRouter(prefix="/api", tags=["public-api"])

_TTL_ACCOUNT = 900  # match the cookie endpoint


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


def _account_hash(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()


def _rate_limit_for_tier(tier: str, settings: Any) -> RateLimit:
    if tier == "high_rpm":
        limit = int(getattr(settings, "rl_api_high_rpm", 600))
    elif tier == "pro":
        limit = int(getattr(settings, "rl_api_pro", 100))
    else:
        limit = int(getattr(settings, "rl_api_free", 10))
    return RateLimit(scope=f"api.tier.{tier}", limit_per_minute=limit)


@router.get("/breachedaccount/{account}", response_model=AccountLookupResponse)
async def public_account_lookup(
    request: Request,
    response: Response,
    api_key: ApiKeyDep,
    hibp: HIBPDep,
    redis_client: RedisDep,
    settings: SettingsDep,
    session: SessionDep,
    account: str = Path(min_length=3, max_length=254),
    truncate_response: bool = Query(default=False, alias="truncateResponse"),
    include_unverified: bool = Query(default=True, alias="includeUnverified"),
) -> AccountLookupResponse:
    rl = _rate_limit_for_tier(api_key.tier, settings)
    # Re-key the limit by API key id rather than IP so multiple servers see one bucket.
    request.scope.setdefault("client", ("api-key", 0))
    request.scope["client"] = (str(api_key.id), 0)
    used = await enforce(redis_client, request, rl)

    remaining = max(0, rl.limit_per_minute - used)
    response.headers["X-RateLimit-Limit"] = str(rl.limit_per_minute)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    response.headers["X-API-Tier"] = api_key.tier

    await record_call(redis_client, session, api_key_id=api_key.id)

    cache_key = (
        f"acct:{_account_hash(account)}:t{int(truncate_response)}:u{int(include_unverified)}"
    )
    cached = await cache_get_json(redis_client, cache_key)
    if cached is not None:
        breaches = [_summary(b) for b in cached]
        return AccountLookupResponse(email=account, breaches=breaches, cached=True)

    try:
        raw = await hibp.breached_account(
            account,
            truncate_response=truncate_response,
            include_unverified=include_unverified,
        )
    except HIBPError as exc:
        raise ProblemError(
            status=502,
            title_key="hibp.upstream_error.title",
            detail_key="hibp.upstream_error.detail",
        ) from exc

    await cache_set_json(redis_client, cache_key, raw, _TTL_ACCOUNT)
    return AccountLookupResponse(email=account, breaches=[_summary(b) for b in raw], cached=False)
