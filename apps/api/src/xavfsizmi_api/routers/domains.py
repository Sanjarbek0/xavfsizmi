"""Account-scoped domain ownership management.

Each domain row carries a single verification method + token. The user can
register a new domain, list their domains, kick off verification, and remove
domains. Methods supported: ``dns_txt``, ``email``, ``meta_tag``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import Response as FastAPIResponse
from pydantic import BaseModel, Field

from ..core.errors import ProblemError
from ..core.i18n import DEFAULT, SUPPORTED, Locale
from ..core.rate_limit import client_ip
from ..db.models import Domain
from ..deps import (
    CurrentUserDep,
    DomainVerifierDep,
    EmailDep,
    SessionDep,
)
from ..services.audit import write_audit
from ..services.domains import (
    DNS_TXT_NAME,
    META_TAG_NAME,
    VerificationMethod,
    attempt_verification,
    list_domains,
    register_domain,
    remove_domain,
)
from ..services.email import EmailMessageSpec, render_domain_verification_email

router = APIRouter(prefix="/account/domains", tags=["account"])


class DomainSummary(BaseModel):
    id: uuid.UUID
    name: str
    verification_method: VerificationMethod
    verification_token: str
    verified_at: datetime | None
    created_at: datetime
    instructions: dict[str, str]


class DomainListResponse(BaseModel):
    items: list[DomainSummary]


class RegisterDomainPayload(BaseModel):
    name: str = Field(min_length=3, max_length=253)
    verification_method: VerificationMethod
    locale: Locale = "uz"
    notify_email: str | None = Field(default=None, max_length=254)


class RegisterDomainResponse(BaseModel):
    domain: DomainSummary


class VerifyDomainPayload(BaseModel):
    submitted_token: str | None = Field(default=None, max_length=128)


class VerifyDomainResponse(BaseModel):
    status: Literal["verified", "pending", "failed"]
    detail: str | None
    domain: DomainSummary


def _instructions(name: str, method: VerificationMethod, token: str) -> dict[str, str]:
    if method == "dns_txt":
        return {
            "host": f"{DNS_TXT_NAME}.{name}",
            "type": "TXT",
            "value": token,
        }
    if method == "meta_tag":
        return {
            "tag": (f'<meta name="{META_TAG_NAME}" content="{token}" />'),
            "url": f"https://{name}/",
        }
    return {"deliver_to": "the email we sent", "code": token}


def _to_summary(domain: Domain) -> DomainSummary:
    method: VerificationMethod = "dns_txt"
    if domain.verification_method in ("dns_txt", "email", "meta_tag"):
        method = domain.verification_method  # type: ignore[assignment]
    return DomainSummary(
        id=domain.id,
        name=domain.name,
        verification_method=method,
        verification_token=domain.verification_token,
        verified_at=domain.verified_at,
        created_at=domain.created_at,
        instructions=_instructions(domain.name, method, domain.verification_token),
    )


def _normalise_locale(value: str | None) -> Locale:
    if value in SUPPORTED:
        return value  # type: ignore[return-value]
    return DEFAULT


@router.get("", response_model=DomainListResponse)
async def list_account_domains(
    user: CurrentUserDep,
    session: SessionDep,
) -> DomainListResponse:
    rows = await list_domains(session, user_id=user.id)
    return DomainListResponse(items=[_to_summary(d) for d in rows])


@router.post("", response_model=RegisterDomainResponse, status_code=201)
async def register_account_domain(
    payload: RegisterDomainPayload,
    request: Request,
    user: CurrentUserDep,
    session: SessionDep,
    email_sender: EmailDep,
) -> RegisterDomainResponse:
    try:
        domain = await register_domain(
            session,
            user_id=user.id,
            name=payload.name,
            method=payload.verification_method,
        )
    except ValueError as exc:
        if str(exc) == "domain already registered":
            raise ProblemError(status=409, title_key="domain.duplicate.title") from exc
        raise ProblemError(
            status=422,
            title_key="domain.invalid.title",
            detail_key="domain.invalid.detail",
        ) from exc

    locale = _normalise_locale(payload.locale)
    if payload.verification_method == "email" and payload.notify_email:
        subject, text, html = render_domain_verification_email(
            domain=domain.name, token=domain.verification_token, locale=locale
        )
        await email_sender.send(
            EmailMessageSpec(
                to=payload.notify_email,
                subject=subject,
                text=text,
                html=html,
            )
        )

    await write_audit(
        session,
        action="domain.register",
        actor_user_id=user.id,
        actor_ip=client_ip(request),
        target_type="domain",
        target_id=str(domain.id),
        detail={"name": domain.name, "method": domain.verification_method},
    )
    return RegisterDomainResponse(domain=_to_summary(domain))


@router.post("/{domain_id}/verify", response_model=VerifyDomainResponse)
async def verify_account_domain(
    domain_id: uuid.UUID,
    payload: VerifyDomainPayload,
    request: Request,
    user: CurrentUserDep,
    session: SessionDep,
    verifier: DomainVerifierDep,
) -> VerifyDomainResponse:
    domain, result = await attempt_verification(
        session,
        user_id=user.id,
        domain_id=domain_id,
        verifier=verifier,
        submitted_token=payload.submitted_token,
    )
    if domain is None:
        raise ProblemError(status=404, title_key="domain.not_found.title")
    status: Literal["verified", "pending", "failed"]
    if result.ok:
        status = "verified"
    else:
        status = "failed"
    await write_audit(
        session,
        action="domain.verify",
        actor_user_id=user.id,
        actor_ip=client_ip(request),
        target_type="domain",
        target_id=str(domain.id),
        detail={"status": status, "detail": result.detail},
    )
    return VerifyDomainResponse(status=status, detail=result.detail, domain=_to_summary(domain))


@router.delete("/{domain_id}", status_code=204)
async def delete_account_domain(
    domain_id: uuid.UUID,
    request: Request,
    user: CurrentUserDep,
    session: SessionDep,
) -> FastAPIResponse:
    ok = await remove_domain(session, user_id=user.id, domain_id=domain_id)
    if not ok:
        raise ProblemError(status=404, title_key="domain.not_found.title")
    await write_audit(
        session,
        action="domain.remove",
        actor_user_id=user.id,
        actor_ip=client_ip(request),
        target_type="domain",
        target_id=str(domain_id),
    )
    return FastAPIResponse(status_code=204)
