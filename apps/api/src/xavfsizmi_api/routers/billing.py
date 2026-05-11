"""Billing endpoints: Stripe checkout, billing portal, webhook.

The integration is intentionally light-weight: the Stripe SDK is loaded lazily
inside ``services.billing`` so the app can run (and tests can pass) without the
SDK being installed. Webhooks are processed idempotently via the
``billing_events`` table.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal, cast

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from ..core.errors import ProblemError
from ..core.rate_limit import client_ip
from ..db.models import BillingEvent, User
from ..deps import BillingDep, CurrentUserDep, SessionDep, SettingsDep
from ..services.api_keys import TIERS, Tier, set_all_keys_tier
from ..services.audit import write_audit
from ..services.billing import PAID_TIERS, tier_price_id

SubscriptionStatus = Literal["inactive", "trialing", "active", "past_due", "canceled", "unpaid"]

router = APIRouter(prefix="/account/billing", tags=["billing"])
webhook_router = APIRouter(prefix="/webhooks", tags=["billing"])


class CheckoutPayload(BaseModel):
    tier: Tier = "pro"
    success_path: str | None = Field(default=None, max_length=512)
    cancel_path: str | None = Field(default=None, max_length=512)


class CheckoutResponse(BaseModel):
    checkout_url: str
    session_id: str


class PortalResponse(BaseModel):
    portal_url: str


class TierLimit(BaseModel):
    tier: Tier
    requests_per_minute: int


class SubscriptionResponse(BaseModel):
    tier: str
    status: str
    current_period_end: datetime | None
    has_customer: bool
    available_tiers: list[TierLimit]


def _base_url(request: Request, settings_origins: list[str]) -> str:
    origin = request.headers.get("origin")
    if origin:
        return origin.rstrip("/")
    if settings_origins:
        return settings_origins[0].rstrip("/")
    return "http://localhost:5173"


@router.get("/subscription", response_model=SubscriptionResponse)
async def get_subscription(user: CurrentUserDep, settings: SettingsDep) -> SubscriptionResponse:
    return SubscriptionResponse(
        tier=user.subscription_tier,
        status=user.subscription_status,
        current_period_end=user.subscription_current_period_end,
        has_customer=user.stripe_customer_id is not None,
        available_tiers=[
            TierLimit(tier="free", requests_per_minute=settings.rl_api_free),
            TierLimit(tier="pro", requests_per_minute=settings.rl_api_pro),
            TierLimit(tier="high_rpm", requests_per_minute=settings.rl_api_high_rpm),
        ],
    )


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(
    payload: CheckoutPayload,
    request: Request,
    user: CurrentUserDep,
    session: SessionDep,
    settings: SettingsDep,
    billing: BillingDep,
) -> CheckoutResponse:
    if payload.tier not in TIERS:
        raise ProblemError(status=422, title_key="billing.invalid_tier.title")
    if payload.tier not in PAID_TIERS:
        raise ProblemError(
            status=422,
            title_key="billing.invalid_tier.title",
            detail_key="billing.invalid_tier.detail",
        )
    if not billing.is_configured:
        raise ProblemError(
            status=503,
            title_key="billing.unavailable.title",
            detail_key="billing.unavailable.detail",
        )
    if not tier_price_id(settings, payload.tier):
        raise ProblemError(
            status=503,
            title_key="billing.unavailable.title",
            detail_key="billing.unavailable.detail",
        )

    base = _base_url(request, settings.allowed_origins_list)
    success_path = payload.success_path or "/account/billing"
    cancel_path = payload.cancel_path or "/account/billing"
    link = await billing.create_checkout_session(
        user,
        tier=payload.tier,
        success_url=f"{base}{success_path}",
        cancel_url=f"{base}{cancel_path}",
    )
    await write_audit(
        session,
        action="billing.checkout.create",
        actor_user_id=user.id,
        actor_ip=client_ip(request),
        target_type="user",
        target_id=str(user.id),
        detail={"tier": payload.tier, "session_id": link.session_id},
    )
    return CheckoutResponse(checkout_url=link.url, session_id=link.session_id)


@router.post("/portal", response_model=PortalResponse)
async def create_portal(
    request: Request,
    user: CurrentUserDep,
    session: SessionDep,
    settings: SettingsDep,
    billing: BillingDep,
) -> PortalResponse:
    if not billing.is_configured:
        raise ProblemError(
            status=503,
            title_key="billing.unavailable.title",
            detail_key="billing.unavailable.detail",
        )
    if not user.stripe_customer_id:
        raise ProblemError(
            status=409,
            title_key="billing.no_customer.title",
            detail_key="billing.no_customer.detail",
        )
    base = _base_url(request, settings.allowed_origins_list)
    return_url = settings.stripe_billing_portal_return_url or f"{base}/account/billing"
    link = await billing.create_portal_session(user, return_url=return_url)
    await write_audit(
        session,
        action="billing.portal.create",
        actor_user_id=user.id,
        actor_ip=client_ip(request),
        target_type="user",
        target_id=str(user.id),
    )
    return PortalResponse(portal_url=link.url)


def _coerce_period_end(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value), UTC)
    except (TypeError, ValueError):
        return None


async def _apply_subscription_event(
    session: SessionDep, *, customer_id: str, payload: dict[str, Any]
) -> User | None:
    user = (
        await session.execute(select(User).where(User.stripe_customer_id == customer_id))
    ).scalar_one_or_none()
    if user is None:
        # Find by metadata.user_id as a fallback.
        meta = payload.get("metadata") or {}
        user_id_raw = meta.get("user_id")
        if user_id_raw:
            try:
                user_id = uuid.UUID(user_id_raw)
            except (ValueError, TypeError):
                return None
            user = (
                await session.execute(select(User).where(User.id == user_id))
            ).scalar_one_or_none()
            if user is not None:
                user.stripe_customer_id = customer_id
    if user is None:
        return None

    status = str(payload.get("status") or "inactive")
    user.subscription_status = status
    items = (payload.get("items") or {}).get("data") or []
    tier: str | None = None
    if items:
        price = (items[0] or {}).get("price") or {}
        lookup_key = price.get("lookup_key")
        if isinstance(lookup_key, str) and lookup_key in TIERS:
            tier = lookup_key
    meta = payload.get("metadata") or {}
    meta_tier = meta.get("tier")
    if isinstance(meta_tier, str) and meta_tier in TIERS:
        tier = meta_tier
    if tier is not None:
        user.subscription_tier = tier
    period_end = _coerce_period_end(payload.get("current_period_end"))
    if period_end is not None:
        user.subscription_current_period_end = period_end
    if status in {"canceled", "incomplete_expired"}:
        user.subscription_tier = "free"
    # Whenever the subscription tier shifts, mirror it onto every active API
    # key the user owns so rate-limit decisions in ``public_api`` line up with
    # what the billing system says.
    new_tier = cast(Tier, user.subscription_tier)
    await set_all_keys_tier(session, user_id=user.id, tier=new_tier)
    return user


@webhook_router.post("/stripe")
async def stripe_webhook(
    request: Request,
    session: SessionDep,
    billing: BillingDep,
    stripe_signature: str = Header(default="", alias="Stripe-Signature"),
) -> dict[str, str]:
    if not billing.is_configured:
        raise ProblemError(
            status=503,
            title_key="billing.unavailable.title",
            detail_key="billing.unavailable.detail",
        )
    payload = await request.body()
    try:
        event = billing.verify_webhook(payload, stripe_signature)
    except Exception as exc:
        raise ProblemError(
            status=400,
            title_key="billing.webhook.invalid.title",
            detail_key="billing.webhook.invalid.detail",
        ) from exc

    seen = (
        await session.execute(select(BillingEvent).where(BillingEvent.id == event.id))
    ).scalar_one_or_none()
    if seen is not None:
        return {"status": "duplicate"}

    obj = cast(dict[str, Any], event.data.get("object") or {})
    customer_id_raw = obj.get("customer")
    customer_id = customer_id_raw if isinstance(customer_id_raw, str) else None
    user: User | None = None
    if event.type.startswith("customer.subscription.") and customer_id:
        user = await _apply_subscription_event(session, customer_id=customer_id, payload=obj)
    elif event.type == "checkout.session.completed" and customer_id:
        # Mark the user's status as active immediately; the subscription.* event
        # that follows will fill in tier + period_end.
        user = (
            await session.execute(select(User).where(User.stripe_customer_id == customer_id))
        ).scalar_one_or_none()
        if user is None:
            meta = obj.get("metadata") or {}
            user_id_raw = meta.get("user_id")
            if user_id_raw:
                try:
                    uid = uuid.UUID(user_id_raw)
                except (ValueError, TypeError):
                    uid = None
                if uid is not None:
                    user = (
                        await session.execute(select(User).where(User.id == uid))
                    ).scalar_one_or_none()
                    if user is not None:
                        user.stripe_customer_id = customer_id
        if user is not None:
            user.subscription_status = "active"

    session.add(
        BillingEvent(
            id=event.id,
            event_type=event.type,
            user_id=user.id if user is not None else None,
            payload=obj,
        )
    )
    await write_audit(
        session,
        action=f"billing.webhook.{event.type}",
        actor_user_id=user.id if user is not None else None,
        target_type="user" if user is not None else None,
        target_id=str(user.id) if user is not None else None,
        detail={"event_id": event.id},
    )
    return {"status": "ok"}


__all__ = ["router", "webhook_router"]
