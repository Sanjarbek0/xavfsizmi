"""ORM models for the Xavfsizmi API.

These mirror the schema documented in ARCHITECTURE.md. Tables are intentionally
narrow: anything that does not need to persist (rate-limit counters, Turnstile
replay protection, HTTP response caches) lives in Redis instead.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

# SQLite ignores autoincrement on BIGINT columns, so for portability we let it
# use plain INTEGER (sqlite3 ROWID semantics). Postgres still gets BIGINT.
_BIGINT_AUTOINCR = BigInteger().with_variant(Integer(), "sqlite")


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Branding(Base):
    """Single-row table holding the deployment's brand identity.

    Decoupled from settings so an admin can rebrand without redeploying.
    """

    __tablename__ = "branding"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    brand_name: Mapped[str] = mapped_column(String(64), nullable=False, default="Xavfsizmi")
    slogan_uz: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    slogan_ru: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    slogan_en: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    primary_color: Mapped[str] = mapped_column(String(16), nullable=False, default="#0d1f2d")
    accent_color: Mapped[str] = mapped_column(String(16), nullable=False, default="#36b37e")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
    )

    __table_args__ = (CheckConstraint("id = 1", name="branding_singleton"),)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(254), nullable=False, unique=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MagicLinkToken(Base):
    """Single-use, short-lived token for passwordless email login."""

    __tablename__ = "magic_link_tokens"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    label: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    key_prefix: Mapped[str] = mapped_column(String(12), nullable=False, unique=True)
    key_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    tier: Mapped[str] = mapped_column(String(16), nullable=False, default="free")
    is_revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("tier in ('free','pro','high_rpm')", name="api_keys_tier_check"),
    )


class ApiKeyUsage(Base):
    """Daily aggregate of API calls per key (per-minute counters live in Redis)."""

    __tablename__ = "api_key_usage"

    id: Mapped[int] = mapped_column(_BIGINT_AUTOINCR, primary_key=True, autoincrement=True)
    api_key_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("api_keys.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    day: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    request_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    __table_args__ = (UniqueConstraint("api_key_id", "day", name="uq_api_key_usage_key_day"),)


class Domain(Base):
    """Domain registered by a user for domain-wide breach search."""

    __tablename__ = "domains"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(253), nullable=False)
    verification_method: Mapped[str] = mapped_column(String(16), nullable=False)
    verification_token: Mapped[str] = mapped_column(String(128), nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_domains_user_name"),
        CheckConstraint(
            "verification_method in ('dns_txt','email','meta_tag')",
            name="domains_method_check",
        ),
    )


class NotificationSubscription(Base):
    """Subscriber that wants to be emailed when their address shows up in a new breach."""

    __tablename__ = "notification_subs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    locale: Mapped[str] = mapped_column(String(8), nullable=False, default="uz")
    confirm_token_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    unsubscribe_token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    __table_args__ = (
        UniqueConstraint("email", name="uq_notification_subs_email"),
        CheckConstraint("locale in ('uz','ru','en')", name="notification_subs_locale_check"),
    )


class BreachCache(Base):
    """Lightweight cache mirror of HIBP breach metadata, refreshed by a job."""

    __tablename__ = "breaches_cache"

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    domain: Mapped[str | None] = mapped_column(String(253), nullable=True)
    breach_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    pwn_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    is_verified: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_sensitive: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_classes: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    refreshed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )


class PasteCache(Base):
    """Per-account paste lookup cache (HIBP /pasteaccount), keyed by account hash."""

    __tablename__ = "paste_cache"

    account_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    payload: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    refreshed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(_BIGINT_AUTOINCR, primary_key=True, autoincrement=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    actor_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=func.now(),
    )

    __table_args__ = (Index("ix_audit_log_action_created", "action", "created_at"),)


__all__ = [
    "ApiKey",
    "ApiKeyUsage",
    "AuditLog",
    "Branding",
    "BreachCache",
    "Domain",
    "MagicLinkToken",
    "NotificationSubscription",
    "PasteCache",
    "User",
]


# Silence "imported but unused" relationship() helper — kept for future expansion.
_ = relationship
