"""Notification subscription stubs (full impl in phase 4)."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, EmailStr

from ..core.i18n import SUPPORTED, Locale

router = APIRouter(prefix="/notifications", tags=["notifications"])


class SubscribeRequest(BaseModel):
    email: EmailStr
    locale: Locale = "uz"


class SubscribeResponse(BaseModel):
    status: str
    locale: Locale


@router.post("/subscribe", response_model=SubscribeResponse)
async def subscribe(payload: SubscribeRequest) -> SubscribeResponse:
    locale = payload.locale if payload.locale in SUPPORTED else "uz"
    # TODO(phase-4): persist sub, send double opt-in email
    return SubscribeResponse(status="pending_confirmation", locale=locale)
