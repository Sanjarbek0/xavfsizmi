"""Notification subscription endpoints (double opt-in flow lands in phase 4)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, EmailStr, Field

from ..core.errors import ProblemError
from ..core.i18n import DEFAULT, SUPPORTED, Locale
from ..core.rate_limit import RateLimit, client_ip, enforce
from ..deps import RedisDep, SettingsDep, TurnstileDep

router = APIRouter(prefix="/notifications", tags=["notifications"])


class SubscribeRequest(BaseModel):
    email: EmailStr
    locale: Locale = "uz"
    turnstile_token: str | None = Field(default=None, alias="turnstileToken")

    model_config = {"populate_by_name": True}


class SubscribeResponse(BaseModel):
    message: str
    status: str
    locale: Locale


RL_SUBSCRIBE = RateLimit(scope="notifications.subscribe", limit_per_minute=5)

_MESSAGES: dict[str, dict[Locale, str]] = {
    "pending_confirmation": {
        "uz": "Tasdiqlash havolasini yubordik. Pochtangizni tekshiring.",
        "ru": "Мы отправили подтверждающую ссылку. Проверьте почту.",
        "en": "We sent a confirmation link. Please check your inbox.",
    }
}


@router.post("/subscribe", response_model=SubscribeResponse)
async def subscribe(
    payload: SubscribeRequest,
    request: Request,
    redis: RedisDep,
    turnstile: TurnstileDep,
    settings: SettingsDep,
) -> SubscribeResponse:
    locale: Locale = payload.locale if payload.locale in SUPPORTED else DEFAULT
    await enforce(redis, request, RL_SUBSCRIBE)
    if settings.turnstile_secret_key:
        ok = await turnstile.verify(payload.turnstile_token, remote_ip=client_ip(request))
        if not ok:
            raise ProblemError(
                status=403,
                title_key="turnstile.failed.title",
                detail_key="turnstile.failed.detail",
            )
    # TODO(phase-4): persist subscription, send double opt-in email via SMTP
    return SubscribeResponse(
        status="pending_confirmation",
        locale=locale,
        message=_MESSAGES["pending_confirmation"][locale],
    )
