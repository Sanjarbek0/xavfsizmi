"""Account-scoped API key management.

All routes require an authenticated session cookie. The plaintext key is only
ever returned at creation time; subsequent reads expose only the public prefix.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import cast

from fastapi import APIRouter, Request
from fastapi.responses import Response as FastAPIResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from ..core.errors import ProblemError
from ..core.rate_limit import client_ip
from ..db.models import ApiKey
from ..deps import CurrentUserDep, RedisDep, SessionDep, SettingsDep
from ..services.api_keys import (
    TIERS,
    Tier,
    create_key,
    list_keys,
    revoke_key,
    tier_at_or_below,
)
from ..services.audit import write_audit
from ..services.usage import current_minute, history, today_count

router = APIRouter(prefix="/account/api-keys", tags=["account"])


class ApiKeySummary(BaseModel):
    id: uuid.UUID
    label: str
    key_prefix: str
    tier: Tier
    is_revoked: bool
    created_at: datetime
    last_used_at: datetime | None


class ApiKeyListResponse(BaseModel):
    items: list[ApiKeySummary]


class CreateKeyPayload(BaseModel):
    label: str = Field(default="", max_length=64)
    # When the client omits ``tier`` we fall back to the user's subscription
    # tier (handled in the handler) so a "Pro" subscriber gets a Pro key by
    # default without having to pick it from a dropdown.
    tier: Tier | None = None


class CreateKeyResponse(BaseModel):
    key: ApiKeySummary
    plaintext: str


def _to_summary(record: ApiKey) -> ApiKeySummary:
    tier: Tier = "free"
    if record.tier in ("free", "pro", "high_rpm"):
        tier = record.tier  # type: ignore[assignment]
    return ApiKeySummary(
        id=record.id,
        label=record.label,
        key_prefix=record.key_prefix,
        tier=tier,
        is_revoked=record.is_revoked,
        created_at=record.created_at,
        last_used_at=record.last_used_at,
    )


@router.get("", response_model=ApiKeyListResponse)
async def list_api_keys(
    user: CurrentUserDep,
    session: SessionDep,
) -> ApiKeyListResponse:
    rows = await list_keys(session, user_id=user.id)
    return ApiKeyListResponse(items=[_to_summary(k) for k in rows])


@router.post("", response_model=CreateKeyResponse, status_code=201)
async def create_api_key(
    payload: CreateKeyPayload,
    request: Request,
    user: CurrentUserDep,
    session: SessionDep,
) -> CreateKeyResponse:
    desired: Tier
    if payload.tier is None:
        sub_tier = user.subscription_tier if user.subscription_tier in TIERS else "free"
        desired = cast(Tier, sub_tier)
    else:
        desired = payload.tier
    if desired not in TIERS:
        raise ProblemError(status=422)
    # A user can only provision keys at or below their current subscription tier.
    if not tier_at_or_below(desired, user.subscription_tier):
        raise ProblemError(
            status=403,
            title_key="api_keys.tier_above_subscription.title",
            detail_key="api_keys.tier_above_subscription.detail",
        )
    issued = await create_key(session, user_id=user.id, label=payload.label, tier=desired)
    await write_audit(
        session,
        action="api_key.create",
        actor_user_id=user.id,
        actor_ip=client_ip(request),
        target_type="api_key",
        target_id=str(issued.record.id),
        detail={"label": payload.label, "tier": desired},
    )
    return CreateKeyResponse(key=_to_summary(issued.record), plaintext=issued.plaintext)


class UsagePoint(BaseModel):
    day: date
    request_count: int


class UsageResponse(BaseModel):
    items: list[UsagePoint]
    total: int
    today: int
    current_minute: int
    tier: Tier
    requests_per_minute: int
    remaining_this_minute: int


def _tier_limit(tier: str, settings: SettingsDep) -> int:
    if tier == "high_rpm":
        return int(settings.rl_api_high_rpm)
    if tier == "pro":
        return int(settings.rl_api_pro)
    return int(settings.rl_api_free)


@router.get("/{key_id}/usage", response_model=UsageResponse)
async def get_api_key_usage(
    key_id: uuid.UUID,
    user: CurrentUserDep,
    session: SessionDep,
    redis: RedisDep,
    settings: SettingsDep,
    days: int = 30,
) -> UsageResponse:
    record = (
        await session.execute(select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user.id))
    ).scalar_one_or_none()
    if record is None:
        raise ProblemError(status=404)
    points = await history(session, api_key_id=key_id, days=days)
    today_value = await today_count(redis, api_key_id=key_id)
    minute_value = await current_minute(redis, tier=record.tier, ip=str(key_id))
    tier_value: Tier = cast(Tier, record.tier if record.tier in TIERS else "free")
    rl_limit = _tier_limit(tier_value, settings)
    remaining = max(0, rl_limit - minute_value)
    total = sum(p.request_count for p in points)
    return UsageResponse(
        items=[UsagePoint(day=p.day, request_count=p.request_count) for p in points],
        total=total,
        today=today_value,
        current_minute=minute_value,
        tier=tier_value,
        requests_per_minute=rl_limit,
        remaining_this_minute=remaining,
    )


@router.delete("/{key_id}", status_code=204)
async def delete_api_key(
    key_id: uuid.UUID,
    request: Request,
    user: CurrentUserDep,
    session: SessionDep,
) -> FastAPIResponse:
    ok = await revoke_key(session, user_id=user.id, key_id=key_id)
    if not ok:
        raise ProblemError(status=404)
    await write_audit(
        session,
        action="api_key.revoke",
        actor_user_id=user.id,
        actor_ip=client_ip(request),
        target_type="api_key",
        target_id=str(key_id),
    )
    return FastAPIResponse(status_code=204)
