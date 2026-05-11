"""Admin endpoints — only accessible by users with `is_admin = true`."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select

from ..core.errors import ProblemError
from ..core.rate_limit import client_ip
from ..db.models import (
    ApiKey,
    AuditLog,
    BreachCache,
    Domain,
    NotificationSubscription,
    User,
)
from ..deps import CurrentUserDep, SessionDep
from ..services.audit import write_audit

router = APIRouter(prefix="/admin", tags=["admin"])


def _require_admin(user: User) -> None:
    if not user.is_admin:
        raise ProblemError(
            status=403,
            title_key="admin.forbidden.title",
            detail_key="admin.forbidden.detail",
        )


class AdminUserRow(BaseModel):
    id: uuid.UUID
    email: str
    is_admin: bool
    is_blocked: bool
    created_at: datetime
    last_login_at: datetime | None


class AdminUserListResponse(BaseModel):
    users: list[AdminUserRow]


class AdminAuditRow(BaseModel):
    id: int
    actor_user_id: uuid.UUID | None
    actor_ip: str | None
    action: str
    target_type: str | None
    target_id: str | None
    detail: dict[str, Any] | None
    created_at: datetime


class AdminAuditListResponse(BaseModel):
    entries: list[AdminAuditRow]


class AdminBreachRow(BaseModel):
    name: str
    title: str | None
    domain: str | None
    breach_date: str | None
    pwn_count: int | None
    is_verified: bool | None
    is_sensitive: bool | None
    description: str | None
    data_classes: list[str] | None


class AdminBreachListResponse(BaseModel):
    breaches: list[AdminBreachRow]


class AdminBreachUpsertRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    title: str | None = None
    domain: str | None = None
    breach_date: str | None = None
    pwn_count: int | None = None
    is_verified: bool | None = None
    is_sensitive: bool | None = None
    description: str | None = None
    data_classes: list[str] | None = None


class AdminMetricsResponse(BaseModel):
    user_count: int
    api_key_count: int
    domain_count: int
    notification_subscriber_count: int
    cached_breach_count: int


class BlockUserRequest(BaseModel):
    blocked: bool


@router.get("/metrics", response_model=AdminMetricsResponse)
async def metrics(user: CurrentUserDep, session: SessionDep) -> AdminMetricsResponse:
    _require_admin(user)
    user_count = (await session.execute(select(func.count(User.id)))).scalar_one()
    api_key_count = (await session.execute(select(func.count(ApiKey.id)))).scalar_one()
    domain_count = (await session.execute(select(func.count(Domain.id)))).scalar_one()
    notification_subscriber_count = (
        await session.execute(
            select(func.count(NotificationSubscription.id)).where(
                NotificationSubscription.confirmed_at.is_not(None)
            )
        )
    ).scalar_one()
    cached_breach_count = (await session.execute(select(func.count(BreachCache.name)))).scalar_one()
    return AdminMetricsResponse(
        user_count=int(user_count),
        api_key_count=int(api_key_count),
        domain_count=int(domain_count),
        notification_subscriber_count=int(notification_subscriber_count),
        cached_breach_count=int(cached_breach_count),
    )


@router.get("/users", response_model=AdminUserListResponse)
async def list_users(
    user: CurrentUserDep,
    session: SessionDep,
) -> AdminUserListResponse:
    _require_admin(user)
    rows = (
        await session.execute(select(User).order_by(desc(User.created_at)).limit(200))
    ).scalars()
    return AdminUserListResponse(users=[_user_row(u) for u in rows])


@router.post("/users/{user_id}/block", response_model=AdminUserRow)
async def block_user(
    user_id: uuid.UUID,
    payload: BlockUserRequest,
    request: Request,
    user: CurrentUserDep,
    session: SessionDep,
) -> AdminUserRow:
    _require_admin(user)
    target = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if target is None:
        raise ProblemError(
            status=404,
            title_key="auth.unauthorized.title",
            detail_key="auth.unauthorized.detail",
        )
    target.is_blocked = payload.blocked
    await write_audit(
        session,
        actor_user_id=user.id,
        actor_ip=client_ip(request),
        action="admin.users.block" if payload.blocked else "admin.users.unblock",
        target_type="user",
        target_id=str(target.id),
        detail=None,
    )
    return _user_row(target)


@router.get("/audit", response_model=AdminAuditListResponse)
async def list_audit(
    user: CurrentUserDep,
    session: SessionDep,
    limit: int = 100,
) -> AdminAuditListResponse:
    _require_admin(user)
    capped = max(1, min(limit, 500))
    rows = (
        await session.execute(select(AuditLog).order_by(desc(AuditLog.created_at)).limit(capped))
    ).scalars()
    return AdminAuditListResponse(
        entries=[
            AdminAuditRow(
                id=int(row.id),
                actor_user_id=row.actor_user_id,
                actor_ip=row.actor_ip,
                action=row.action,
                target_type=row.target_type,
                target_id=row.target_id,
                detail=row.detail,
                created_at=row.created_at,
            )
            for row in rows
        ]
    )


@router.get("/breaches", response_model=AdminBreachListResponse)
async def list_breaches(
    user: CurrentUserDep,
    session: SessionDep,
) -> AdminBreachListResponse:
    _require_admin(user)
    rows = (
        await session.execute(select(BreachCache).order_by(desc(BreachCache.refreshed_at)))
    ).scalars()
    return AdminBreachListResponse(
        breaches=[
            AdminBreachRow(
                name=row.name,
                title=row.title,
                domain=row.domain,
                breach_date=row.breach_date,
                pwn_count=row.pwn_count,
                is_verified=row.is_verified,
                is_sensitive=row.is_sensitive,
                description=row.description,
                data_classes=row.data_classes,
            )
            for row in rows
        ]
    )


@router.post("/breaches", response_model=AdminBreachRow)
async def upsert_breach(
    payload: AdminBreachUpsertRequest,
    request: Request,
    user: CurrentUserDep,
    session: SessionDep,
) -> AdminBreachRow:
    _require_admin(user)
    existing = (
        await session.execute(select(BreachCache).where(BreachCache.name == payload.name))
    ).scalar_one_or_none()
    if existing is None:
        existing = BreachCache(name=payload.name)
        session.add(existing)

    existing.title = payload.title
    existing.domain = payload.domain
    existing.breach_date = payload.breach_date
    existing.pwn_count = payload.pwn_count
    existing.is_verified = payload.is_verified
    existing.is_sensitive = payload.is_sensitive
    existing.description = payload.description
    existing.data_classes = payload.data_classes
    existing.payload = payload.model_dump(exclude={"name"})

    await write_audit(
        session,
        actor_user_id=user.id,
        actor_ip=client_ip(request),
        action="admin.breaches.upsert",
        target_type="breach",
        target_id=payload.name,
        detail=None,
    )
    return AdminBreachRow(
        name=existing.name,
        title=existing.title,
        domain=existing.domain,
        breach_date=existing.breach_date,
        pwn_count=existing.pwn_count,
        is_verified=existing.is_verified,
        is_sensitive=existing.is_sensitive,
        description=existing.description,
        data_classes=existing.data_classes,
    )


def _user_row(record: User) -> AdminUserRow:
    return AdminUserRow(
        id=record.id,
        email=record.email,
        is_admin=record.is_admin,
        is_blocked=record.is_blocked,
        created_at=record.created_at,
        last_login_at=record.last_login_at,
    )


__all__ = ["router"]
