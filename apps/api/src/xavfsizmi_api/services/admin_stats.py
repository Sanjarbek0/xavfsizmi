"""Aggregate queries powering the admin "Stats" tab.

Each query is independent so the router can fire them in parallel if needed.
The shapes are flat dataclasses to keep Pydantic serialisation simple and to
make the result easy to test without spinning up FastAPI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import (
    ApiKey,
    BreachCache,
    NotificationSubscription,
    User,
)


@dataclass(slots=True)
class DailyPoint:
    day: str  # ISO date, YYYY-MM-DD
    count: int


@dataclass(slots=True)
class UserStats:
    total_users: int = 0
    blocked_users: int = 0
    admin_users: int = 0
    active_subscribers: int = 0
    pending_subscribers: int = 0
    by_tier: dict[str, int] = field(default_factory=dict)
    by_subscription_status: dict[str, int] = field(default_factory=dict)
    signups_last_30_days: list[DailyPoint] = field(default_factory=list)


@dataclass(slots=True)
class TopBreach:
    name: str
    title: str | None
    pwn_count: int | None
    breach_date: str | None


@dataclass(slots=True)
class BreachStats:
    total_breaches: int = 0
    sensitive_breaches: int = 0
    verified_breaches: int = 0
    total_pwn_count: int = 0
    top_by_pwn_count: list[TopBreach] = field(default_factory=list)
    breaches_added_last_30_days: list[DailyPoint] = field(default_factory=list)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _format_day(value: datetime) -> str:
    return value.astimezone(UTC).date().isoformat()


def _empty_30_day_series(now: datetime) -> dict[str, int]:
    today = now.astimezone(UTC).date()
    return {(today - timedelta(days=i)).isoformat(): 0 for i in range(30)}


async def compute_user_stats(session: AsyncSession) -> UserStats:
    stats = UserStats()
    stats.total_users = int((await session.execute(select(func.count(User.id)))).scalar_one() or 0)
    stats.blocked_users = int(
        (
            await session.execute(select(func.count(User.id)).where(User.is_blocked.is_(True)))
        ).scalar_one()
        or 0
    )
    stats.admin_users = int(
        (
            await session.execute(select(func.count(User.id)).where(User.is_admin.is_(True)))
        ).scalar_one()
        or 0
    )
    stats.active_subscribers = int(
        (
            await session.execute(
                select(func.count(NotificationSubscription.id)).where(
                    NotificationSubscription.confirmed_at.is_not(None)
                )
            )
        ).scalar_one()
        or 0
    )
    stats.pending_subscribers = int(
        (
            await session.execute(
                select(func.count(NotificationSubscription.id)).where(
                    NotificationSubscription.confirmed_at.is_(None)
                )
            )
        ).scalar_one()
        or 0
    )

    tier_rows = (
        await session.execute(
            select(ApiKey.tier, func.count(ApiKey.id))
            .where(ApiKey.is_revoked.is_(False))
            .group_by(ApiKey.tier)
        )
    ).all()
    stats.by_tier = {tier: int(count) for tier, count in tier_rows}

    sub_rows = (
        await session.execute(
            select(User.subscription_status, func.count(User.id)).group_by(User.subscription_status)
        )
    ).all()
    stats.by_subscription_status = {status: int(count) for status, count in sub_rows}

    now = _utcnow()
    series = _empty_30_day_series(now)
    cutoff = now - timedelta(days=30)
    signup_rows = (
        await session.execute(select(User.created_at).where(User.created_at >= cutoff))
    ).scalars()
    for created in signup_rows:
        day = _format_day(created)
        if day in series:
            series[day] += 1
    stats.signups_last_30_days = [
        DailyPoint(day=day, count=count) for day, count in sorted(series.items())
    ]
    return stats


async def compute_breach_stats(session: AsyncSession, *, top_n: int = 10) -> BreachStats:
    stats = BreachStats()
    stats.total_breaches = int(
        (await session.execute(select(func.count(BreachCache.name)))).scalar_one() or 0
    )
    stats.sensitive_breaches = int(
        (
            await session.execute(
                select(func.count(BreachCache.name)).where(BreachCache.is_sensitive.is_(True))
            )
        ).scalar_one()
        or 0
    )
    stats.verified_breaches = int(
        (
            await session.execute(
                select(func.count(BreachCache.name)).where(BreachCache.is_verified.is_(True))
            )
        ).scalar_one()
        or 0
    )
    stats.total_pwn_count = int(
        (
            await session.execute(select(func.coalesce(func.sum(BreachCache.pwn_count), 0)))
        ).scalar_one()
        or 0
    )

    top_rows = (
        await session.execute(
            select(BreachCache)
            .where(BreachCache.pwn_count.is_not(None))
            .order_by(desc(BreachCache.pwn_count))
            .limit(top_n)
        )
    ).scalars()
    stats.top_by_pwn_count = [
        TopBreach(
            name=row.name,
            title=row.title,
            pwn_count=row.pwn_count,
            breach_date=row.breach_date,
        )
        for row in top_rows
    ]

    now = _utcnow()
    series = _empty_30_day_series(now)
    cutoff = now - timedelta(days=30)
    added_rows = (
        await session.execute(
            select(BreachCache.refreshed_at).where(BreachCache.refreshed_at >= cutoff)
        )
    ).scalars()
    for refreshed in added_rows:
        day = _format_day(refreshed)
        if day in series:
            series[day] += 1
    stats.breaches_added_last_30_days = [
        DailyPoint(day=day, count=count) for day, count in sorted(series.items())
    ]
    return stats


__all__ = [
    "BreachStats",
    "DailyPoint",
    "TopBreach",
    "UserStats",
    "compute_breach_stats",
    "compute_user_stats",
]
