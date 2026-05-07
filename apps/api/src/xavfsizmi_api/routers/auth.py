"""Magic-link authentication endpoints.

Flow:
1. ``POST /v1/auth/request`` — caller submits an email + locale + Turnstile
   token. We mint a one-time link, email it, and reply with a generic
   "check your inbox" message regardless of whether the user existed.
2. ``GET /v1/auth/verify?token=...`` — caller (typically the email link target)
   submits the token. We mark the token consumed, set the session cookie, and
   redirect or respond.
3. ``POST /v1/auth/logout`` — clears the session cookie.
4. ``GET /v1/auth/me`` — returns the authenticated user, or 401.

The router never reveals whether a given email is registered.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from urllib.parse import quote, urlparse

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, EmailStr, Field

from ..core.errors import ProblemError
from ..core.i18n import DEFAULT, SUPPORTED, Locale
from ..core.rate_limit import RateLimit, client_ip, enforce
from ..deps import (
    CurrentUserDep,
    EmailDep,
    RedisDep,
    SessionDep,
    SettingsDep,
    TurnstileDep,
)
from ..services.audit import write_audit
from ..services.auth import (
    SESSION_COOKIE_NAME,
    SESSION_TTL_SECONDS,
    consume_magic_link,
    issue_magic_link,
    issue_session_cookie,
)
from ..services.email import EmailMessageSpec, render_magic_link_email

router = APIRouter(prefix="/auth", tags=["auth"])

RL_REQUEST = RateLimit(scope="auth.request", limit_per_minute=5)
RL_VERIFY = RateLimit(scope="auth.verify", limit_per_minute=10)


class RequestLinkPayload(BaseModel):
    email: EmailStr
    locale: Locale = "uz"
    turnstile_token: str | None = Field(default=None, alias="turnstileToken")
    redirect_path: str | None = Field(default=None, alias="redirectPath", max_length=512)

    model_config = {"populate_by_name": True}


class RequestLinkResponse(BaseModel):
    status: str
    message: str
    locale: Locale


class VerifyResponse(BaseModel):
    status: str
    user_id: uuid.UUID
    email: str
    is_admin: bool


class MeResponse(BaseModel):
    user_id: uuid.UUID
    email: str
    is_admin: bool
    last_login_at: datetime | None


_REQUEST_MESSAGES: dict[Locale, str] = {
    "uz": "Agar bu email tizimda mavjud bo'lsa, kirish havolasini yubordik.",
    "ru": "Если такой email зарегистрирован, мы отправили на него ссылку для входа.",
    "en": "If that email exists, we just sent a sign-in link.",
}


def _normalise_locale(value: str | None) -> Locale:
    if value in SUPPORTED:
        return value  # type: ignore[return-value]
    return DEFAULT


def _safe_redirect_path(raw: str | None) -> str:
    """Allow only relative same-origin paths to avoid open-redirect."""
    if not raw:
        return "/"
    parsed = urlparse(raw)
    if parsed.scheme or parsed.netloc:
        return "/"
    if not raw.startswith("/"):
        return "/"
    return raw


def _build_link(*, base_url: str, token: str, locale: Locale, redirect_path: str) -> str:
    base = base_url.rstrip("/")
    return (
        f"{base}/{locale}/account/verify"
        f"?token={quote(token, safe='')}"
        f"&next={quote(redirect_path, safe='')}"
    )


def _set_session_cookie(response: Response, value: str, *, settings: SettingsDep) -> None:
    secure = settings.env in ("staging", "production")
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=value,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )


@router.post("/request", response_model=RequestLinkResponse)
async def request_magic_link(
    payload: RequestLinkPayload,
    request: Request,
    redis: RedisDep,
    turnstile: TurnstileDep,
    session: SessionDep,
    email_sender: EmailDep,
    settings: SettingsDep,
) -> RequestLinkResponse:
    locale = _normalise_locale(payload.locale)
    await enforce(redis, request, RL_REQUEST)
    if settings.turnstile_secret_key:
        ok = await turnstile.verify(payload.turnstile_token, remote_ip=client_ip(request))
        if not ok:
            raise ProblemError(
                status=403,
                title_key="turnstile.failed.title",
                detail_key="turnstile.failed.detail",
            )

    issued = await issue_magic_link(session, email=payload.email)
    origins = settings.allowed_origins_list
    base_url = request.headers.get("origin") or (origins[0] if origins else "http://localhost:5173")
    redirect = _safe_redirect_path(payload.redirect_path)
    link = _build_link(base_url=base_url, token=issued.token, locale=locale, redirect_path=redirect)
    subject, text, html = render_magic_link_email(link=link, locale=locale)
    await email_sender.send(
        EmailMessageSpec(
            to=issued.user.email,
            subject=subject,
            text=text,
            html=html,
        )
    )
    await write_audit(
        session,
        action="auth.magic_link.request",
        actor_user_id=issued.user.id,
        actor_ip=client_ip(request),
        target_type="user",
        target_id=str(issued.user.id),
        detail={"locale": locale, "is_new_user": issued.is_new_user},
    )
    return RequestLinkResponse(
        status="ok",
        message=_REQUEST_MESSAGES[locale],
        locale=locale,
    )


class VerifyPayload(BaseModel):
    token: str


@router.post("/verify", response_model=VerifyResponse)
async def verify_magic_link(
    payload: VerifyPayload,
    request: Request,
    response: Response,
    redis: RedisDep,
    session: SessionDep,
    settings: SettingsDep,
) -> VerifyResponse:
    await enforce(redis, request, RL_VERIFY)
    user = await consume_magic_link(session, token=payload.token)
    if user is None:
        raise ProblemError(
            status=400,
            title_key="auth.invalid_token.title",
            detail_key="auth.invalid_token.detail",
        )
    cookie_value = issue_session_cookie(user.id, settings=settings)
    _set_session_cookie(response, cookie_value, settings=settings)
    await write_audit(
        session,
        action="auth.magic_link.verify",
        actor_user_id=user.id,
        actor_ip=client_ip(request),
        target_type="user",
        target_id=str(user.id),
    )
    return VerifyResponse(
        status="ok",
        user_id=user.id,
        email=user.email,
        is_admin=user.is_admin,
    )


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
) -> dict[str, str]:
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    await write_audit(
        session,
        action="auth.logout",
        actor_ip=client_ip(request),
    )
    _ = settings  # signature symmetry
    return {"status": "ok"}


@router.get("/me", response_model=MeResponse)
async def me(user: CurrentUserDep) -> MeResponse:
    return MeResponse(
        user_id=user.id,
        email=user.email,
        is_admin=user.is_admin,
        last_login_at=user.last_login_at,
    )
