"""Notification subscription service — double opt-in flow."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.i18n import Locale
from ..db.models import NotificationSubscription


def _now() -> datetime:
    return datetime.now(UTC)


def _generate_token() -> str:
    return secrets.token_urlsafe(32)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass(slots=True)
class IssuedSubscription:
    subscription: NotificationSubscription
    confirm_token: str
    unsubscribe_token: str
    is_new: bool


async def request_subscription(
    session: AsyncSession,
    *,
    email: str,
    locale: Locale,
) -> IssuedSubscription:
    """Create or refresh a pending subscription and return both tokens (plaintext)."""
    normalized = email.strip().lower()
    confirm_token = _generate_token()
    unsubscribe_token = _generate_token()
    confirm_hash = _hash_token(confirm_token)
    unsubscribe_hash = _hash_token(unsubscribe_token)

    existing = (
        await session.execute(
            select(NotificationSubscription).where(NotificationSubscription.email == normalized)
        )
    ).scalar_one_or_none()

    if existing is None:
        sub = NotificationSubscription(
            email=normalized,
            locale=locale,
            confirm_token_hash=confirm_hash,
            unsubscribe_token_hash=unsubscribe_hash,
        )
        session.add(sub)
        return IssuedSubscription(
            subscription=sub,
            confirm_token=confirm_token,
            unsubscribe_token=unsubscribe_token,
            is_new=True,
        )

    existing.locale = locale
    if existing.confirmed_at is None:
        existing.confirm_token_hash = confirm_hash
        existing.unsubscribe_token_hash = unsubscribe_hash
        return IssuedSubscription(
            subscription=existing,
            confirm_token=confirm_token,
            unsubscribe_token=unsubscribe_token,
            is_new=False,
        )

    return IssuedSubscription(
        subscription=existing,
        confirm_token="",
        unsubscribe_token=unsubscribe_token,
        is_new=False,
    )


async def confirm_subscription(
    session: AsyncSession, *, token: str
) -> NotificationSubscription | None:
    token_hash = _hash_token(token)
    sub = (
        await session.execute(
            select(NotificationSubscription).where(
                NotificationSubscription.confirm_token_hash == token_hash
            )
        )
    ).scalar_one_or_none()
    if sub is None:
        return None
    if sub.confirmed_at is None:
        sub.confirmed_at = _now()
    sub.confirm_token_hash = None
    return sub


async def unsubscribe(session: AsyncSession, *, token: str) -> NotificationSubscription | None:
    token_hash = _hash_token(token)
    sub = (
        await session.execute(
            select(NotificationSubscription).where(
                NotificationSubscription.unsubscribe_token_hash == token_hash
            )
        )
    ).scalar_one_or_none()
    if sub is None:
        return None
    await session.delete(sub)
    return sub


async def list_confirmed_subscriptions(session: AsyncSession) -> list[NotificationSubscription]:
    rows = (
        await session.execute(
            select(NotificationSubscription).where(
                NotificationSubscription.confirmed_at.is_not(None)
            )
        )
    ).scalars()
    return list(rows)


__all__ = [
    "IssuedSubscription",
    "confirm_subscription",
    "list_confirmed_subscriptions",
    "request_subscription",
    "unsubscribe",
]
