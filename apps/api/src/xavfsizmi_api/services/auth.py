"""Authentication primitives — magic-link tokens + signed session cookies.

We keep the surface minimal: opaque random tokens for magic links (hashed before
storage, looked up by hash on verify) and a stateless signed session cookie
carrying the user id and expiry. Both rely on stdlib + ``itsdangerous`` so
there's no external auth service.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

from itsdangerous import BadSignature, SignatureExpired, TimestampSigner
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..db.models import MagicLinkToken, User

SESSION_COOKIE_NAME: Final[str] = "xv_session"
MAGIC_LINK_TTL_SECONDS: Final[int] = 15 * 60
SESSION_TTL_SECONDS: Final[int] = 30 * 24 * 60 * 60  # 30 days


def _now() -> datetime:
    return datetime.now(UTC)


def _signer(settings: Settings) -> TimestampSigner:
    return TimestampSigner(settings.session_secret, salt="xavfsizmi.session")


def issue_session_cookie(user_id: uuid.UUID, *, settings: Settings) -> str:
    return _signer(settings).sign(str(user_id)).decode("utf-8")


def read_session_cookie(value: str | None, *, settings: Settings) -> uuid.UUID | None:
    if not value:
        return None
    try:
        raw = _signer(settings).unsign(value, max_age=SESSION_TTL_SECONDS)
    except SignatureExpired:
        return None
    except BadSignature:
        return None
    try:
        return uuid.UUID(raw.decode("utf-8"))
    except (ValueError, AttributeError):
        return None


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _generate_token() -> str:
    """Return a URL-safe opaque random token."""
    return secrets.token_urlsafe(32)


def constant_time_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


@dataclass(slots=True)
class IssuedMagicLink:
    user: User
    token: str
    expires_at: datetime
    is_new_user: bool


async def issue_magic_link(session: AsyncSession, *, email: str) -> IssuedMagicLink:
    """Find or create the user, then mint+store a fresh magic-link token."""
    normalized = email.strip().lower()
    user = (
        await session.execute(select(User).where(User.email == normalized))
    ).scalar_one_or_none()
    is_new_user = False
    if user is None:
        user = User(email=normalized)
        session.add(user)
        await session.flush()
        is_new_user = True

    token = _generate_token()
    expires_at = _now() + timedelta(seconds=MAGIC_LINK_TTL_SECONDS)
    record = MagicLinkToken(
        user_id=user.id,
        token_hash=_hash_token(token),
        expires_at=expires_at,
    )
    session.add(record)
    return IssuedMagicLink(user=user, token=token, expires_at=expires_at, is_new_user=is_new_user)


def _as_utc(value: datetime) -> datetime:
    """Treat naive datetimes (e.g. from SQLite drivers) as UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


async def consume_magic_link(session: AsyncSession, *, token: str) -> User | None:
    """Look up + consume a magic-link token; returns the matching user or None."""
    token_hash = _hash_token(token)
    record = (
        await session.execute(select(MagicLinkToken).where(MagicLinkToken.token_hash == token_hash))
    ).scalar_one_or_none()
    if record is None:
        return None
    if record.consumed_at is not None:
        return None
    if _as_utc(record.expires_at) <= _now():
        return None

    user = (
        await session.execute(select(User).where(User.id == record.user_id))
    ).scalar_one_or_none()
    if user is None:
        return None
    if user.is_blocked:
        return None

    record.consumed_at = _now()
    user.last_login_at = _now()
    return user


__all__ = [
    "MAGIC_LINK_TTL_SECONDS",
    "SESSION_COOKIE_NAME",
    "SESSION_TTL_SECONDS",
    "IssuedMagicLink",
    "constant_time_eq",
    "consume_magic_link",
    "issue_magic_link",
    "issue_session_cookie",
    "read_session_cookie",
]
