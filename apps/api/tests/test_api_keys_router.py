"""Account-scoped API key CRUD tests + tier-aware public lookup."""

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


def test_keys_crud_round_trip(
    client: TestClient,
    fake_email: InMemoryEmailSender,
) -> None:
    _login(client, "owner@example.com", fake_email)

    # Empty list initially.
    res = client.get("/v1/account/api-keys")
    assert res.status_code == 200
    assert res.json()["items"] == []

    # Create one.
    create = client.post(
        "/v1/account/api-keys",
        json={"label": "ci-bot", "tier": "free"},
    )
    assert create.status_code == 201
    body = create.json()
    assert body["plaintext"].startswith("xvf_")
    assert body["key"]["key_prefix"] == body["plaintext"][:12]
    assert body["key"]["tier"] == "free"
    assert body["key"]["label"] == "ci-bot"
    key_id = body["key"]["id"]

    # List shows it (and never the plaintext).
    listed = client.get("/v1/account/api-keys").json()
    assert len(listed["items"]) == 1
    assert listed["items"][0]["id"] == key_id
    assert "plaintext" not in listed["items"][0]

    # Revoke it.
    delete = client.delete(f"/v1/account/api-keys/{key_id}")
    assert delete.status_code == 204

    after = client.get("/v1/account/api-keys").json()
    assert after["items"][0]["is_revoked"] is True


def test_keys_require_auth(client: TestClient) -> None:
    res = client.get("/v1/account/api-keys")
    assert res.status_code == 401


def test_create_key_with_invalid_tier_is_rejected(
    client: TestClient,
    fake_email: InMemoryEmailSender,
) -> None:
    _login(client, "tier@example.com", fake_email)
    res = client.post(
        "/v1/account/api-keys",
        json={"label": "x", "tier": "platinum"},
    )
    assert res.status_code == 422


def test_public_api_requires_key(client: TestClient) -> None:
    res = client.get("/v1/api/breachedaccount/foo@example.com")
    assert res.status_code == 401
    body = res.json()
    assert body["title"] in {"API kalit topilmadi", "API key missing", "API-ключ не найден"}


def test_public_api_with_valid_key_returns_data(
    client: TestClient,
    fake_email: InMemoryEmailSender,
    fake_hibp: object,
) -> None:
    _login(client, "user@example.com", fake_email)
    create = client.post(
        "/v1/account/api-keys",
        json={"label": "prod", "tier": "pro"},
    ).json()
    plaintext = create["plaintext"]

    fake_hibp.breached_payload = [  # type: ignore[attr-defined]
        {"Name": "Adobe", "Title": "Adobe", "Domain": "adobe.com"},
    ]
    res = client.get(
        "/v1/api/breachedaccount/test@example.com",
        headers={"x-api-key": plaintext},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["email"] == "test@example.com"
    assert body["breaches"][0]["name"] == "Adobe"


def test_public_api_with_revoked_key_is_unauthorized(
    client: TestClient,
    fake_email: InMemoryEmailSender,
) -> None:
    _login(client, "rev@example.com", fake_email)
    create = client.post("/v1/account/api-keys", json={"label": "x", "tier": "free"}).json()
    key_id = create["key"]["id"]
    plaintext = create["plaintext"]
    client.delete(f"/v1/account/api-keys/{key_id}")

    res = client.get(
        "/v1/api/breachedaccount/test@example.com",
        headers={"x-api-key": plaintext},
    )
    assert res.status_code == 401
