"""Stripe billing skeleton.

Provides a thin abstraction over the Stripe SDK so the rest of the codebase
(and the test suite) can run without ever importing ``stripe`` when the
``stripe_secret_key`` is empty.

The default ``StripeBilling`` implementation lazy-imports the SDK and exposes:

- ``ensure_customer(user)`` — create/return a customer for the user
- ``create_checkout_session(user, tier, success_url, cancel_url)`` — checkout link
- ``create_portal_session(user)`` — Stripe-hosted billing portal link
- ``verify_webhook(payload, signature)`` — verify a webhook signature

For tests / unconfigured environments we provide an in-memory ``FakeBilling``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Protocol

from ..config import Settings
from ..db.models import User
from .api_keys import TIERS, Tier

PAID_TIERS: tuple[Tier, ...] = ("pro", "high_rpm")


@dataclass(slots=True)
class CheckoutLink:
    url: str
    session_id: str


@dataclass(slots=True)
class PortalLink:
    url: str


@dataclass(slots=True)
class StripeEvent:
    id: str
    type: str
    data: dict[str, Any]


class BillingProvider(Protocol):
    @property
    def is_configured(self) -> bool: ...

    async def ensure_customer(self, user: User) -> str: ...

    async def create_checkout_session(
        self, user: User, *, tier: Tier, success_url: str, cancel_url: str
    ) -> CheckoutLink: ...

    async def create_portal_session(self, user: User, *, return_url: str) -> PortalLink: ...

    def verify_webhook(self, payload: bytes, signature: str) -> StripeEvent: ...


def tier_price_id(settings: Settings, tier: Tier) -> str:
    if tier == "pro":
        return settings.stripe_price_pro
    if tier == "high_rpm":
        return settings.stripe_price_high_rpm
    return ""


class StripeBilling:
    """Thin wrapper over the Stripe SDK.

    Each call imports ``stripe`` lazily so the rest of the package (and the test
    runner) never has to depend on the SDK being installed.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def is_configured(self) -> bool:
        return bool(self._settings.stripe_secret_key)

    def _stripe(self) -> Any:
        import stripe

        stripe.api_key = self._settings.stripe_secret_key
        return stripe

    async def ensure_customer(self, user: User) -> str:
        if user.stripe_customer_id:
            return user.stripe_customer_id
        stripe = self._stripe()
        customer = stripe.Customer.create(
            email=user.email,
            metadata={"user_id": str(user.id)},
        )
        customer_id = str(customer["id"])
        user.stripe_customer_id = customer_id
        return customer_id

    async def create_checkout_session(
        self, user: User, *, tier: Tier, success_url: str, cancel_url: str
    ) -> CheckoutLink:
        price = tier_price_id(self._settings, tier)
        if not price:
            raise ValueError(f"no Stripe price configured for tier {tier!r}")
        customer_id = await self.ensure_customer(user)
        stripe = self._stripe()
        session = stripe.checkout.Session.create(
            mode="subscription",
            customer=customer_id,
            line_items=[{"price": price, "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={"user_id": str(user.id), "tier": tier},
        )
        return CheckoutLink(url=session["url"], session_id=session["id"])

    async def create_portal_session(self, user: User, *, return_url: str) -> PortalLink:
        if not user.stripe_customer_id:
            raise ValueError("user has no Stripe customer id")
        stripe = self._stripe()
        portal = stripe.billing_portal.Session.create(
            customer=user.stripe_customer_id, return_url=return_url
        )
        return PortalLink(url=portal["url"])

    def verify_webhook(self, payload: bytes, signature: str) -> StripeEvent:
        if not self._settings.stripe_webhook_secret:
            raise ValueError("stripe_webhook_secret is not configured")
        stripe = self._stripe()
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=signature,
            secret=self._settings.stripe_webhook_secret,
        )
        return StripeEvent(
            id=str(event["id"]),
            type=str(event["type"]),
            data=dict(event["data"]),
        )


class FakeBilling:
    """In-memory billing implementation used in tests + dev when Stripe is off."""

    def __init__(self) -> None:
        self._customers: dict[uuid.UUID, str] = {}
        self.events: list[StripeEvent] = []

    @property
    def is_configured(self) -> bool:
        return False

    async def ensure_customer(self, user: User) -> str:
        if user.stripe_customer_id:
            return user.stripe_customer_id
        cid = self._customers.get(user.id) or f"cus_fake_{user.id.hex[:12]}"
        self._customers[user.id] = cid
        user.stripe_customer_id = cid
        return cid

    async def create_checkout_session(
        self, user: User, *, tier: Tier, success_url: str, cancel_url: str
    ) -> CheckoutLink:
        await self.ensure_customer(user)
        return CheckoutLink(
            url=f"https://fake-stripe.example/checkout/{user.id}/{tier}",
            session_id=f"cs_fake_{user.id.hex[:12]}",
        )

    async def create_portal_session(self, user: User, *, return_url: str) -> PortalLink:
        await self.ensure_customer(user)
        return PortalLink(url=f"https://fake-stripe.example/portal/{user.id}")

    def verify_webhook(self, payload: bytes, signature: str) -> StripeEvent:
        del payload, signature
        raise ValueError("webhook verification unavailable in fake billing")


def build_billing(settings: Settings) -> BillingProvider:
    if settings.stripe_secret_key:
        return StripeBilling(settings)
    return FakeBilling()


__all__ = [
    "PAID_TIERS",
    "TIERS",
    "BillingProvider",
    "CheckoutLink",
    "FakeBilling",
    "PortalLink",
    "StripeBilling",
    "StripeEvent",
    "Tier",
    "build_billing",
    "tier_price_id",
]
