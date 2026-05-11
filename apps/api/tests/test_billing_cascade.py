"""Subscription tier changes cascade to a user's API keys + creation rules."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from xavfsizmi_api.config import get_settings
from xavfsizmi_api.deps import billing_dep
from xavfsizmi_api.main import app as real_app
from xavfsizmi_api.services.billing import FakeBilling, StripeEvent

from .conftest import InMemoryEmailSender, promote_user


def _login(client: TestClient, email: str, fake_email: InMemoryEmailSender) -> None:
    client.post("/v1/auth/request", json={"email": email, "locale": "en"})
    sent = fake_email.outbox[-1]
    marker = "?token="
    start = sent.text.find(marker) + len(marker)
    end = sent.text.find("&", start)
    token = sent.text[start:end]
    res = client.post("/v1/auth/verify", json={"token": token})
    assert res.status_code == 200


@pytest.fixture(autouse=True)
def _reset_settings() -> None:
    get_settings.cache_clear()


class WebhookFakeBilling(FakeBilling):
    """FakeBilling that pretends Stripe is configured + replays a canned event."""

    def __init__(self, event: StripeEvent) -> None:
        super().__init__()
        self._event = event

    @property
    def is_configured(self) -> bool:
        return True

    def verify_webhook(self, payload: bytes, signature: str) -> StripeEvent:
        del payload, signature
        return self._event


def test_create_key_above_subscription_tier_returns_403(
    client: TestClient, fake_email: InMemoryEmailSender
) -> None:
    _login(client, "free@example.com", fake_email)
    res = client.post("/v1/account/api-keys", json={"label": "x", "tier": "pro"})
    assert res.status_code == 403


def test_create_key_defaults_to_subscription_tier(
    client: TestClient,
    fake_email: InMemoryEmailSender,
    db_session: AsyncSession,
) -> None:
    _login(client, "pro@example.com", fake_email)
    asyncio.run(promote_user(db_session, email="pro@example.com", tier="pro"))
    res = client.post("/v1/account/api-keys", json={"label": "default-tier"})
    assert res.status_code == 201
    assert res.json()["key"]["tier"] == "pro"


def test_subscription_endpoint_includes_available_tiers(
    client: TestClient, fake_email: InMemoryEmailSender
) -> None:
    _login(client, "sub@example.com", fake_email)
    body = client.get("/v1/account/billing/subscription").json()
    tiers: list[dict[str, Any]] = body["available_tiers"]
    assert {t["tier"] for t in tiers} == {"free", "pro", "high_rpm"}
    free = next(t for t in tiers if t["tier"] == "free")
    assert free["requests_per_minute"] >= 1


def test_webhook_subscription_update_promotes_existing_keys(
    client: TestClient,
    fake_email: InMemoryEmailSender,
) -> None:
    """A free-tier user with a free key should see the key promoted to pro
    after a ``customer.subscription.updated`` event flips the tier."""
    _login(client, "casc@example.com", fake_email)
    create = client.post("/v1/account/api-keys", json={"label": "k", "tier": "free"}).json()
    key_id = create["key"]["id"]

    me = client.get("/v1/auth/me").json()
    user_id = me["user_id"]

    # Wire a custom FakeBilling that replays a "now on pro" subscription event.
    event = StripeEvent(
        id="evt_test_1",
        type="customer.subscription.updated",
        data={
            "object": {
                "id": "sub_test",
                "customer": "cus_test_casc",
                "status": "active",
                "items": {"data": [{"price": {"lookup_key": "pro"}}]},
                "metadata": {"user_id": user_id, "tier": "pro"},
            }
        },
    )
    fake = WebhookFakeBilling(event)
    real_app.dependency_overrides[billing_dep] = lambda: fake
    try:
        res = client.post(
            "/v1/webhooks/stripe",
            content=b"{}",
            headers={"Stripe-Signature": "sig"},
        )
        assert res.status_code == 200
    finally:
        real_app.dependency_overrides[billing_dep] = lambda: FakeBilling()

    # Subscription tier moved; existing key followed it.
    keys = client.get("/v1/account/api-keys").json()["items"]
    assert next(k for k in keys if k["id"] == key_id)["tier"] == "pro"
    sub = client.get("/v1/account/billing/subscription").json()
    assert sub["tier"] == "pro"
