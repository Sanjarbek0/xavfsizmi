"""Notification subscription endpoints — double opt-in flow."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, EmailStr, Field

from ..core.errors import ProblemError
from ..core.i18n import DEFAULT, SUPPORTED, Locale
from ..core.rate_limit import RateLimit, client_ip, enforce
from ..deps import (
    EmailDep,
    RedisDep,
    SessionDep,
    SettingsDep,
    TurnstileDep,
)
from ..services.audit import write_audit
from ..services.email import EmailMessageSpec, render_notification_confirm_email
from ..services.notifications import (
    confirm_subscription,
    request_subscription,
    unsubscribe,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])


class SubscribeRequest(BaseModel):
    email: EmailStr
    locale: Locale = "uz"
    turnstile_token: str | None = Field(default=None, alias="turnstileToken")
    redirect_path: str | None = Field(default=None, alias="redirectPath")

    model_config = {"populate_by_name": True}


class SubscribeResponse(BaseModel):
    message: str
    status: str
    locale: Locale


class TokenPayload(BaseModel):
    token: str


class TokenResponse(BaseModel):
    status: str
    message: str


RL_SUBSCRIBE = RateLimit(scope="notifications.subscribe", limit_per_minute=5)
RL_TOKEN = RateLimit(scope="notifications.token", limit_per_minute=30)

_MESSAGES: dict[str, dict[Locale, str]] = {
    "pending_confirmation": {
        "uz": "Tasdiqlash havolasini yubordik. Pochtangizni tekshiring.",
        "ru": "Мы отправили подтверждающую ссылку. Проверьте почту.",
        "en": "We sent a confirmation link. Please check your inbox.",
    },
    "already_confirmed": {
        "uz": "Siz allaqachon obuna bo'lgansiz.",
        "ru": "Вы уже подписаны.",
        "en": "You are already subscribed.",
    },
    "confirmed": {
        "uz": "Obuna tasdiqlandi. Rahmat!",
        "ru": "Подписка подтверждена. Спасибо!",
        "en": "Subscription confirmed. Thank you!",
    },
    "unsubscribed": {
        "uz": "Obuna bekor qilindi.",
        "ru": "Подписка отменена.",
        "en": "You have been unsubscribed.",
    },
}


def _build_link(request: Request, settings_origins: list[str], path: str) -> str:
    base = request.headers.get("origin") or (
        settings_origins[0] if settings_origins else "http://localhost:5173"
    )
    return f"{base.rstrip('/')}{path}"


@router.post("/subscribe", response_model=SubscribeResponse)
async def subscribe(
    payload: SubscribeRequest,
    request: Request,
    redis: RedisDep,
    turnstile: TurnstileDep,
    settings: SettingsDep,
    session: SessionDep,
    email: EmailDep,
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

    issued = await request_subscription(session, email=str(payload.email), locale=locale)
    await session.flush()

    status_key = "pending_confirmation"
    if issued.confirm_token:
        confirm_link = _build_link(
            request,
            settings.allowed_origins_list,
            f"/{locale}/confirm?token={issued.confirm_token}",
        )
        unsubscribe_link = _build_link(
            request,
            settings.allowed_origins_list,
            f"/{locale}/unsubscribe?token={issued.unsubscribe_token}",
        )
        subject, text, html = render_notification_confirm_email(
            confirm_link=confirm_link,
            unsubscribe_link=unsubscribe_link,
            locale=locale,
        )
        await email.send(
            EmailMessageSpec(to=str(payload.email), subject=subject, text=text, html=html)
        )
        await write_audit(
            session,
            actor_user_id=None,
            actor_ip=client_ip(request),
            action="notifications.subscribe",
            target_type="notification_sub",
            target_id=str(issued.subscription.id),
            detail={"email_hash_prefix": str(payload.email)[:3] + "…"},
        )
    else:
        status_key = "already_confirmed"

    return SubscribeResponse(
        status=status_key,
        locale=locale,
        message=_MESSAGES[status_key][locale],
    )


@router.post("/confirm", response_model=TokenResponse)
async def confirm(
    payload: TokenPayload,
    request: Request,
    redis: RedisDep,
    session: SessionDep,
) -> TokenResponse:
    await enforce(redis, request, RL_TOKEN)
    sub = await confirm_subscription(session, token=payload.token)
    if sub is None:
        raise ProblemError(
            status=400,
            title_key="notifications.invalid_token.title",
            detail_key="notifications.invalid_token.detail",
        )
    locale = sub.locale if sub.locale in SUPPORTED else DEFAULT
    await write_audit(
        session,
        actor_user_id=None,
        actor_ip=client_ip(request),
        action="notifications.confirm",
        target_type="notification_sub",
        target_id=str(sub.id),
        detail=None,
    )
    return TokenResponse(status="confirmed", message=_MESSAGES["confirmed"][locale])


@router.post("/unsubscribe", response_model=TokenResponse)
async def unsubscribe_route(
    payload: TokenPayload,
    request: Request,
    redis: RedisDep,
    session: SessionDep,
) -> TokenResponse:
    await enforce(redis, request, RL_TOKEN)
    sub = await unsubscribe(session, token=payload.token)
    if sub is None:
        raise ProblemError(
            status=400,
            title_key="notifications.invalid_token.title",
            detail_key="notifications.invalid_token.detail",
        )
    locale = sub.locale if sub.locale in SUPPORTED else DEFAULT
    await write_audit(
        session,
        actor_user_id=None,
        actor_ip=client_ip(request),
        action="notifications.unsubscribe",
        target_type="notification_sub",
        target_id=str(sub.id),
        detail=None,
    )
    return TokenResponse(status="unsubscribed", message=_MESSAGES["unsubscribed"][locale])
