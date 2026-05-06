"""Email-breach lookup endpoints (HIBP proxy)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, EmailStr

from ..core import i18n
from ..services.hibp_client import HIBPClient, HIBPError

router = APIRouter(prefix="/breaches", tags=["breaches"])


class AccountLookupRequest(BaseModel):
    email: EmailStr
    turnstile_token: str | None = None


class BreachSummary(BaseModel):
    name: str
    title: str | None = None
    domain: str | None = None
    breach_date: str | None = None
    pwn_count: int | None = None
    is_verified: bool | None = None
    is_sensitive: bool | None = None
    data_classes: list[str] | None = None


class AccountLookupResponse(BaseModel):
    email: str
    breaches: list[BreachSummary]


@router.post("/account", response_model=AccountLookupResponse)
async def lookup_account(payload: AccountLookupRequest, request: Request) -> AccountLookupResponse:
    locale = i18n.negotiate(request)
    _ = locale  # negotiated for error responses; reserved for future use
    client = HIBPClient.from_settings()
    try:
        breaches = await client.breached_account(str(payload.email))
    except HIBPError as e:
        if e.status == 404:
            return AccountLookupResponse(email=str(payload.email), breaches=[])
        raise HTTPException(
            status_code=e.status or status.HTTP_502_BAD_GATEWAY,
            detail=str(e),
        ) from e
    finally:
        await client.aclose()

    summaries = [
        BreachSummary(
            name=b.get("Name", ""),
            title=b.get("Title"),
            domain=b.get("Domain"),
            breach_date=b.get("BreachDate"),
            pwn_count=b.get("PwnCount"),
            is_verified=b.get("IsVerified"),
            is_sensitive=b.get("IsSensitive"),
            data_classes=b.get("DataClasses"),
        )
        for b in breaches
    ]
    return AccountLookupResponse(email=str(payload.email), breaches=summaries)
