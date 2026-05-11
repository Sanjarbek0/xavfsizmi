"""Billing checkout / portal / webhook endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from xavfsizmi_api.config import get_settings

from .conftest import InMemoryEmailSender


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


def test_subscription_endpoint_returns_defaults(
    client: TestClient, fake_email: InMemoryEmailSender
) -> None:
    _login(client, "free@example.com", fake_email)
    res = client.get("/v1/account/billing/subscription")
    assert res.status_code == 200
    body = res.json()
    assert body["tier"] == "free"
    assert body["status"] == "inactive"
    assert body["has_customer"] is False


def test_checkout_with_unconfigured_billing_returns_503(
    client: TestClient, fake_email: InMemoryEmailSender
) -> None:
    _login(client, "checkout@example.com", fake_email)
    res = client.post("/v1/account/billing/checkout", json={"tier": "pro"})
    assert res.status_code == 503


def test_checkout_rejects_free_tier(client: TestClient, fake_email: InMemoryEmailSender) -> None:
    _login(client, "freetier@example.com", fake_email)
    res = client.post("/v1/account/billing/checkout", json={"tier": "free"})
    assert res.status_code == 422


def test_portal_requires_existing_customer(
    client: TestClient, fake_email: InMemoryEmailSender
) -> None:
    _login(client, "portal@example.com", fake_email)
    res = client.post("/v1/account/billing/portal")
    # Without Stripe configured this is 503 first.
    assert res.status_code == 503


def test_webhook_without_billing_configured_returns_503(client: TestClient) -> None:
    res = client.post(
        "/v1/webhooks/stripe",
        content=b'{"id": "evt_test"}',
        headers={"Stripe-Signature": "sig"},
    )
    assert res.status_code == 503
