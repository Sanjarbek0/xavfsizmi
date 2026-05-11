"""Admin endpoints — only accessible by users with `is_admin = true`."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, File, Query, Request, UploadFile
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
from ..deps import CurrentUserDep, EmailDep, SessionDep, SettingsDep
from ..services.admin_stats import compute_breach_stats, compute_user_stats
from ..services.audit import write_audit
from ..services.csv_breach_import import import_breaches, parse_breach_csv
from ..services.notifications_dispatch import dispatch_breach_notifications

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


# ---------------------------------------------------------------------------
# CSV breach import
# ---------------------------------------------------------------------------


class CsvImportErrorOut(BaseModel):
    line: int
    message: str


class CsvImportResponse(BaseModel):
    inserted: int
    updated: int
    skipped: int
    dry_run: bool
    headers: list[str]
    errors: list[CsvImportErrorOut]
    inserted_names: list[str]
    updated_names: list[str]


@router.post("/breaches/upload", response_model=CsvImportResponse)
async def upload_breaches_csv(
    request: Request,
    user: CurrentUserDep,
    session: SessionDep,
    file: UploadFile = File(...),
    dry_run: bool = Query(default=False),
) -> CsvImportResponse:
    _require_admin(user)
    body = await file.read()
    if not body:
        raise ProblemError(
            status=400,
            title_key="admin.csv.empty.title",
            detail_key="admin.csv.empty.detail",
        )

    parsed = parse_breach_csv(body)
    blocking = [
        e
        for e in parsed.errors
        if e.message.startswith("missing_required_column") or e.message == "empty_file"
    ]
    if blocking:
        raise ProblemError(
            status=400,
            title_key="admin.csv.invalid.title",
            detail_key="admin.csv.invalid.detail",
            extras={
                "headers": parsed.headers,
                "errors": [{"line": e.line, "message": e.message} for e in parsed.errors],
            },
        )

    outcome = await import_breaches(session, parsed.rows, dry_run=dry_run)

    if not dry_run and (outcome.inserted or outcome.updated):
        await write_audit(
            session,
            actor_user_id=user.id,
            actor_ip=client_ip(request),
            action="admin.breaches.csv_upload",
            target_type="breach",
            target_id=None,
            detail={
                "inserted": outcome.inserted,
                "updated": outcome.updated,
                "filename": file.filename,
            },
        )

    return CsvImportResponse(
        inserted=outcome.inserted,
        updated=outcome.updated,
        skipped=len(parsed.errors),
        dry_run=dry_run,
        headers=parsed.headers,
        errors=[CsvImportErrorOut(line=e.line, message=e.message) for e in parsed.errors],
        inserted_names=outcome.inserted_names,
        updated_names=outcome.updated_names,
    )


# ---------------------------------------------------------------------------
# Manual breach notification dispatch
# ---------------------------------------------------------------------------


class DispatchRequest(BaseModel):
    breach_name: str = Field(min_length=1, max_length=64)
    dry_run: bool = False
    limit: int | None = Field(default=None, ge=1, le=10_000)


class DispatchRecipient(BaseModel):
    email: str
    sent: bool
    error: str | None = None


class DispatchResponse(BaseModel):
    breach_name: str
    breach_title: str
    total_subscribers: int
    sent: int
    failed: int
    skipped: int
    dry_run: bool
    recipients: list[DispatchRecipient]


def _frontend_base(request: Request, settings_origins: list[str]) -> str:
    origin = request.headers.get("origin")
    if origin:
        return origin
    if settings_origins:
        return settings_origins[0]
    return "http://localhost:5173"


@router.post("/notifications/dispatch", response_model=DispatchResponse)
async def dispatch_notifications(
    payload: DispatchRequest,
    request: Request,
    user: CurrentUserDep,
    session: SessionDep,
    settings: SettingsDep,
    email: EmailDep,
) -> DispatchResponse:
    _require_admin(user)
    base = _frontend_base(request, settings.allowed_origins_list)
    outcome = await dispatch_breach_notifications(
        session,
        email,
        breach_name=payload.breach_name,
        base_url=base,
        dry_run=payload.dry_run,
        limit=payload.limit,
    )
    if outcome is None:
        raise ProblemError(
            status=404,
            title_key="admin.dispatch.unknown_breach.title",
            detail_key="admin.dispatch.unknown_breach.detail",
        )

    if not payload.dry_run:
        await write_audit(
            session,
            actor_user_id=user.id,
            actor_ip=client_ip(request),
            action="admin.notifications.dispatch",
            target_type="breach",
            target_id=outcome.breach_name,
            detail={
                "sent": outcome.sent,
                "failed": outcome.failed,
                "total": outcome.total_subscribers,
                "limit": payload.limit,
            },
        )

    return DispatchResponse(
        breach_name=outcome.breach_name,
        breach_title=outcome.breach_title,
        total_subscribers=outcome.total_subscribers,
        sent=outcome.sent,
        failed=outcome.failed,
        skipped=outcome.skipped,
        dry_run=outcome.dry_run,
        recipients=[
            DispatchRecipient(email=r.email, sent=r.sent, error=r.error)
            for r in outcome.per_recipient
        ],
    )


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


class StatsDailyPoint(BaseModel):
    day: str
    count: int


class StatsTopBreach(BaseModel):
    name: str
    title: str | None
    pwn_count: int | None
    breach_date: str | None


class UserStatsResponse(BaseModel):
    total_users: int
    blocked_users: int
    admin_users: int
    active_subscribers: int
    pending_subscribers: int
    by_tier: dict[str, int]
    by_subscription_status: dict[str, int]
    signups_last_30_days: list[StatsDailyPoint]


class BreachStatsResponse(BaseModel):
    total_breaches: int
    sensitive_breaches: int
    verified_breaches: int
    total_pwn_count: int
    top_by_pwn_count: list[StatsTopBreach]
    breaches_added_last_30_days: list[StatsDailyPoint]


@router.get("/stats/users", response_model=UserStatsResponse)
async def stats_users(user: CurrentUserDep, session: SessionDep) -> UserStatsResponse:
    _require_admin(user)
    stats = await compute_user_stats(session)
    return UserStatsResponse(
        total_users=stats.total_users,
        blocked_users=stats.blocked_users,
        admin_users=stats.admin_users,
        active_subscribers=stats.active_subscribers,
        pending_subscribers=stats.pending_subscribers,
        by_tier=stats.by_tier,
        by_subscription_status=stats.by_subscription_status,
        signups_last_30_days=[
            StatsDailyPoint(day=p.day, count=p.count) for p in stats.signups_last_30_days
        ],
    )


@router.get("/stats/breaches", response_model=BreachStatsResponse)
async def stats_breaches(
    user: CurrentUserDep,
    session: SessionDep,
    top_n: int = Query(default=10, ge=1, le=100),
) -> BreachStatsResponse:
    _require_admin(user)
    stats = await compute_breach_stats(session, top_n=top_n)
    return BreachStatsResponse(
        total_breaches=stats.total_breaches,
        sensitive_breaches=stats.sensitive_breaches,
        verified_breaches=stats.verified_breaches,
        total_pwn_count=stats.total_pwn_count,
        top_by_pwn_count=[
            StatsTopBreach(
                name=row.name,
                title=row.title,
                pwn_count=row.pwn_count,
                breach_date=row.breach_date,
            )
            for row in stats.top_by_pwn_count
        ],
        breaches_added_last_30_days=[
            StatsDailyPoint(day=p.day, count=p.count) for p in stats.breaches_added_last_30_days
        ],
    )


__all__ = ["router"]
