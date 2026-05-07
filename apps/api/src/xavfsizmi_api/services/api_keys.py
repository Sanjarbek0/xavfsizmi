"""Issuance, hashing, and validation of public API keys.

Plaintext keys look like ``xvf_<base32>``; only the prefix and an Argon2 hash
of the full key are stored. The plaintext is shown once at creation time.
"""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final, Literal

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import ApiKey

KEY_PREFIX: Final[str] = "xvf_"
KEY_BODY_BYTES: Final[int] = 24  # ~32 base32 chars
TIERS: Final[tuple[str, ...]] = ("free", "pro", "high_rpm")
Tier = Literal["free", "pro", "high_rpm"]

_HASHER = PasswordHasher()


@dataclass(slots=True)
class IssuedApiKey:
    record: ApiKey
    plaintext: str


def _generate_plaintext() -> tuple[str, str]:
    """Return ``(plaintext, public_prefix)``.

    The public prefix is the first 12 characters of the plaintext (incl. the
    ``xvf_`` brand) — short enough to display in a UI list and stored on the
    key record so we can identify which key produced a request without having
    to reverse the hash.
    """
    body = secrets.token_urlsafe(KEY_BODY_BYTES).rstrip("=").replace("-", "").replace("_", "")
    plaintext = f"{KEY_PREFIX}{body}"
    return plaintext, plaintext[:12]


def hash_key(plaintext: str) -> str:
    return _HASHER.hash(plaintext)


def verify_key(plaintext: str, hashed: str) -> bool:
    try:
        return _HASHER.verify(hashed, plaintext)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


async def list_keys(session: AsyncSession, *, user_id: uuid.UUID) -> list[ApiKey]:
    rows = (
        await session.execute(
            select(ApiKey).where(ApiKey.user_id == user_id).order_by(ApiKey.created_at.desc())
        )
    ).scalars()
    return list(rows)


async def create_key(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    label: str,
    tier: Tier = "free",
) -> IssuedApiKey:
    if tier not in TIERS:
        raise ValueError(f"unknown tier: {tier}")
    plaintext, prefix = _generate_plaintext()
    record = ApiKey(
        user_id=user_id,
        label=label.strip()[:64],
        key_prefix=prefix,
        key_hash=hash_key(plaintext),
        tier=tier,
    )
    session.add(record)
    await session.flush()
    return IssuedApiKey(record=record, plaintext=plaintext)


async def revoke_key(session: AsyncSession, *, user_id: uuid.UUID, key_id: uuid.UUID) -> bool:
    record = (
        await session.execute(select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user_id))
    ).scalar_one_or_none()
    if record is None:
        return False
    record.is_revoked = True
    return True


async def authenticate_key(session: AsyncSession, *, plaintext: str) -> ApiKey | None:
    """Look up a key by prefix and verify the hash. Returns None on mismatch."""
    if not plaintext.startswith(KEY_PREFIX) or len(plaintext) < len(KEY_PREFIX) + 8:
        return None
    prefix = plaintext[:12]
    record = (
        await session.execute(select(ApiKey).where(ApiKey.key_prefix == prefix))
    ).scalar_one_or_none()
    if record is None or record.is_revoked:
        return None
    if not verify_key(plaintext, record.key_hash):
        return None
    record.last_used_at = datetime.now(UTC)
    return record


__all__ = [
    "KEY_PREFIX",
    "TIERS",
    "IssuedApiKey",
    "Tier",
    "authenticate_key",
    "create_key",
    "hash_key",
    "list_keys",
    "revoke_key",
    "verify_key",
]
