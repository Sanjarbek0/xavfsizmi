"""Manual breach notification dispatch.

An admin picks a cached breach and (optionally) a subset of recipients; this
service walks every confirmed subscriber, rotates their unsubscribe token,
renders the per-locale email, and sends it through the configured
``EmailSender``. Dispatches are idempotency-safe in the sense that they only
target ``confirmed_at IS NOT NULL`` rows and they always emit a fresh
unsubscribe token (the previous one is invalidated).
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.i18n import DEFAULT, SUPPORTED, Locale
from ..db.models import BreachCache, NotificationSubscription
from .email import EmailMessageSpec, EmailSender, render_breach_notification_email


def _new_token() -> str:
    return secrets.token_urlsafe(32)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass(slots=True)
class DispatchOutcome:
    email: str
    sent: bool
    error: str | None = None


@dataclass(slots=True)
class DispatchResult:
    breach_name: str
    breach_title: str
    total_subscribers: int
    sent: int = 0
    failed: int = 0
    skipped: int = 0
    dry_run: bool = False
    per_recipient: list[DispatchOutcome] = field(default_factory=list)


def _build_unsub_link(base_url: str, locale: Locale, token: str) -> str:
    return f"{base_url.rstrip('/')}/{locale}/unsubscribe?token={token}"


async def _load_breach(session: AsyncSession, name: str) -> BreachCache | None:
    return (
        await session.execute(select(BreachCache).where(BreachCache.name == name))
    ).scalar_one_or_none()


async def dispatch_breach_notifications(
    session: AsyncSession,
    sender: EmailSender,
    *,
    breach_name: str,
    base_url: str,
    dry_run: bool = False,
    limit: int | None = None,
) -> DispatchResult | None:
    """Send the breach-notification email to every confirmed subscriber.

    Returns ``None`` if the breach is not in the cache (caller should 404).
    """
    breach = await _load_breach(session, breach_name)
    if breach is None:
        return None

    rows = list(
        (
            await session.execute(
                select(NotificationSubscription).where(
                    NotificationSubscription.confirmed_at.is_not(None)
                )
            )
        ).scalars()
    )

    if limit is not None:
        rows = rows[:limit]

    result = DispatchResult(
        breach_name=breach.name,
        breach_title=breach.title or breach.name,
        total_subscribers=len(rows),
        dry_run=dry_run,
    )

    for sub in rows:
        locale: Locale = sub.locale if sub.locale in SUPPORTED else DEFAULT
        if dry_run:
            result.per_recipient.append(DispatchOutcome(email=sub.email, sent=False))
            result.skipped += 1
            continue

        token = _new_token()
        sub.unsubscribe_token_hash = _hash(token)
        unsubscribe_link = _build_unsub_link(base_url, locale, token)
        subject, text, html = render_breach_notification_email(
            breach_title=result.breach_title,
            breach_date=breach.breach_date,
            unsubscribe_link=unsubscribe_link,
            locale=locale,
        )

        try:
            await sender.send(EmailMessageSpec(to=sub.email, subject=subject, text=text, html=html))
        except Exception as exc:  # pragma: no cover - depends on transport
            result.failed += 1
            result.per_recipient.append(
                DispatchOutcome(email=sub.email, sent=False, error=str(exc)[:200])
            )
            continue

        result.sent += 1
        result.per_recipient.append(DispatchOutcome(email=sub.email, sent=True))

    return result


__all__ = [
    "DispatchOutcome",
    "DispatchResult",
    "dispatch_breach_notifications",
]
