"""Public API usage telemetry: per-key counter and history endpoint."""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

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


def test_public_call_records_usage_and_emits_rate_limit_headers(
    client: TestClient,
    fake_email: InMemoryEmailSender,
    fake_hibp: object,
    db_session: AsyncSession,
) -> None:
    _login(client, "usage@example.com", fake_email)
    asyncio.run(promote_user(db_session, email="usage@example.com", tier="pro"))
    create = client.post("/v1/account/api-keys", json={"label": "u", "tier": "pro"}).json()
    plaintext = create["plaintext"]
    key_id = create["key"]["id"]
    fake_hibp.breached_payload = []  # type: ignore[attr-defined]

    res = client.get(
        "/v1/api/breachedaccount/u@example.com",
        headers={"x-api-key": plaintext},
    )
    assert res.status_code == 200
    assert int(res.headers["x-ratelimit-limit"]) >= 1
    assert int(res.headers["x-ratelimit-remaining"]) >= 0
    assert res.headers["x-api-tier"] == "pro"

    usage = client.get(f"/v1/account/api-keys/{key_id}/usage").json()
    assert usage["items"][0]["request_count"] >= 1


def test_usage_for_other_users_key_is_404(
    client: TestClient,
    fake_email: InMemoryEmailSender,
) -> None:
    _login(client, "owner@example.com", fake_email)
    create = client.post("/v1/account/api-keys", json={"label": "o", "tier": "free"}).json()
    key_id = create["key"]["id"]
    # Logout, then login as someone else.
    client.post("/v1/auth/logout")
    _login(client, "intruder@example.com", fake_email)

    res = client.get(f"/v1/account/api-keys/{key_id}/usage")
    assert res.status_code == 404
