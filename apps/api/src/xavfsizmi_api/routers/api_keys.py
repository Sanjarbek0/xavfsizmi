"""Account-scoped API key management.

All routes require an authenticated session cookie. The plaintext key is only
ever returned at creation time; subsequent reads expose only the public prefix.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import Response as FastAPIResponse
from pydantic import BaseModel, Field

from ..core.errors import ProblemError
from ..core.rate_limit import client_ip
from ..db.models import ApiKey
from ..deps import CurrentUserDep, SessionDep
from ..services.api_keys import (
    TIERS,
    Tier,
    create_key,
    list_keys,
    revoke_key,
)
from ..services.audit import write_audit

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
    tier: Tier = "free"


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
    if payload.tier not in TIERS:
        raise ProblemError(status=422)
    issued = await create_key(session, user_id=user.id, label=payload.label, tier=payload.tier)
    await write_audit(
        session,
        action="api_key.create",
        actor_user_id=user.id,
        actor_ip=client_ip(request),
        target_type="api_key",
        target_id=str(issued.record.id),
        detail={"label": payload.label, "tier": payload.tier},
    )
    return CreateKeyResponse(key=_to_summary(issued.record), plaintext=issued.plaintext)


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
