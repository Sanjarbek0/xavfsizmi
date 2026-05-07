"""Domain ownership verification — DNS TXT, email token, and HTML meta tag.

Each verification method is a small async coroutine returning a boolean. We
isolate the network bits behind an injectable :class:`DomainVerifier` so tests
can swap them with deterministic fakes.
"""

from __future__ import annotations

import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final, Literal, Protocol

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Domain

VerificationMethod = Literal["dns_txt", "email", "meta_tag"]
METHODS: Final[tuple[VerificationMethod, ...]] = ("dns_txt", "email", "meta_tag")
DNS_TXT_NAME: Final[str] = "_xavfsizmi"
META_TAG_NAME: Final[str] = "xavfsizmi-site-verification"

_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$",
    re.IGNORECASE,
)


def is_valid_domain(name: str) -> bool:
    candidate = name.strip().lower().rstrip(".")
    return bool(_DOMAIN_RE.match(candidate))


def normalize_domain(name: str) -> str:
    return name.strip().lower().rstrip(".")


def generate_verification_token() -> str:
    return secrets.token_urlsafe(24)


@dataclass(slots=True)
class VerificationResult:
    ok: bool
    detail: str | None = None


class DomainVerifier(Protocol):
    async def verify_dns_txt(self, *, domain: str, token: str) -> VerificationResult: ...
    async def verify_meta_tag(self, *, domain: str, token: str) -> VerificationResult: ...


class DefaultDomainVerifier:
    """Production verifier: real DNS lookups (dnspython) + HTTP fetch (httpx).

    Email verification doesn't need a network probe — the user enters the token
    we mailed them, and we compare it constant-time-equal to the stored token.
    """

    def __init__(self, *, http_timeout_sec: float = 5.0) -> None:
        self._http_timeout = http_timeout_sec

    async def verify_dns_txt(self, *, domain: str, token: str) -> VerificationResult:
        try:
            import dns.asyncresolver
            import dns.exception
            import dns.rdatatype
        except ImportError:
            return VerificationResult(False, "dnspython is not installed")

        host = f"{DNS_TXT_NAME}.{domain}"
        try:
            answer = await dns.asyncresolver.resolve(host, dns.rdatatype.TXT, lifetime=5)
        except dns.exception.DNSException as exc:
            return VerificationResult(False, f"dns lookup failed: {exc}")

        for rdata in answer:
            for raw in rdata.strings:
                if isinstance(raw, bytes) and raw.decode("utf-8", "ignore") == token:
                    return VerificationResult(True)
                if isinstance(raw, str) and raw == token:
                    return VerificationResult(True)
        return VerificationResult(False, "txt record value mismatch")

    async def verify_meta_tag(self, *, domain: str, token: str) -> VerificationResult:
        url = f"https://{domain}/"
        try:
            async with httpx.AsyncClient(
                timeout=self._http_timeout, follow_redirects=True
            ) as client:
                resp = await client.get(url)
        except httpx.HTTPError as exc:
            return VerificationResult(False, f"http fetch failed: {exc}")
        if resp.status_code >= 400:
            return VerificationResult(False, f"http {resp.status_code}")
        # Naïve scan; we don't pull in an HTML parser for one tag.
        body = resp.text.lower()
        needle = f'<meta name="{META_TAG_NAME}" content="{token.lower()}"'
        if needle in body:
            return VerificationResult(True)
        return VerificationResult(False, "meta tag not found")


async def list_domains(session: AsyncSession, *, user_id: uuid.UUID) -> list[Domain]:
    rows = (
        await session.execute(
            select(Domain).where(Domain.user_id == user_id).order_by(Domain.created_at.desc())
        )
    ).scalars()
    return list(rows)


async def register_domain(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    name: str,
    method: VerificationMethod,
) -> Domain:
    if method not in METHODS:
        raise ValueError(f"unknown verification method: {method}")
    if not is_valid_domain(name):
        raise ValueError("invalid domain")
    canonical = normalize_domain(name)
    existing = (
        await session.execute(
            select(Domain).where(Domain.user_id == user_id, Domain.name == canonical)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ValueError("domain already registered")

    record = Domain(
        user_id=user_id,
        name=canonical,
        verification_method=method,
        verification_token=generate_verification_token(),
    )
    session.add(record)
    await session.flush()
    return record


async def remove_domain(session: AsyncSession, *, user_id: uuid.UUID, domain_id: uuid.UUID) -> bool:
    record = (
        await session.execute(
            select(Domain).where(Domain.id == domain_id, Domain.user_id == user_id)
        )
    ).scalar_one_or_none()
    if record is None:
        return False
    await session.delete(record)
    return True


async def attempt_verification(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    domain_id: uuid.UUID,
    verifier: DomainVerifier,
    submitted_token: str | None = None,
) -> tuple[Domain | None, VerificationResult]:
    record = (
        await session.execute(
            select(Domain).where(Domain.id == domain_id, Domain.user_id == user_id)
        )
    ).scalar_one_or_none()
    if record is None:
        return None, VerificationResult(False, "domain not found")
    if record.verified_at is not None:
        return record, VerificationResult(True, "already verified")

    if record.verification_method == "dns_txt":
        result = await verifier.verify_dns_txt(domain=record.name, token=record.verification_token)
    elif record.verification_method == "meta_tag":
        result = await verifier.verify_meta_tag(domain=record.name, token=record.verification_token)
    elif record.verification_method == "email":
        if submitted_token is None:
            result = VerificationResult(False, "missing token")
        else:
            ok = secrets.compare_digest(submitted_token.strip(), record.verification_token)
            result = VerificationResult(ok, None if ok else "token mismatch")
    else:  # pragma: no cover — defensive
        result = VerificationResult(False, "unknown verification method")

    if result.ok:
        record.verified_at = datetime.now(UTC)
    return record, result


__all__ = [
    "DNS_TXT_NAME",
    "META_TAG_NAME",
    "METHODS",
    "DefaultDomainVerifier",
    "DomainVerifier",
    "VerificationMethod",
    "VerificationResult",
    "attempt_verification",
    "generate_verification_token",
    "is_valid_domain",
    "list_domains",
    "normalize_domain",
    "register_domain",
    "remove_domain",
]
