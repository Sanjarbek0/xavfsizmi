"""Magic-link authentication flow tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from xavfsizmi_api.config import get_settings

from .conftest import InMemoryEmailSender


@pytest.fixture(autouse=True)
def _reset_settings() -> None:
    get_settings.cache_clear()


def test_request_link_emails_user_and_replies_generic(
    client: TestClient,
    fake_email: InMemoryEmailSender,
) -> None:
    res = client.post(
        "/v1/auth/request",
        json={"email": "alice@example.com", "locale": "uz"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["locale"] == "uz"
    # Generic message — never reveals whether the email exists.
    assert "yubordik" in body["message"].lower()
    assert len(fake_email.outbox) == 1
    assert fake_email.outbox[0].to == "alice@example.com"
    assert "Xavfsizmi" in fake_email.outbox[0].subject


def test_request_link_localises_email_subject(
    client: TestClient,
    fake_email: InMemoryEmailSender,
) -> None:
    res = client.post(
        "/v1/auth/request",
        json={"email": "ivan@example.com", "locale": "ru"},
    )
    assert res.status_code == 200
    assert fake_email.outbox[-1].subject.endswith("ссылка для входа")


def test_verify_consumes_token_and_sets_cookie(
    client: TestClient,
    fake_email: InMemoryEmailSender,
) -> None:
    client.post(
        "/v1/auth/request",
        json={"email": "bob@example.com", "locale": "en"},
    )
    sent = fake_email.outbox[-1]
    # Pull the token out of the link in the body text.
    body_text = sent.text
    token_marker = "?token="
    start = body_text.find(token_marker) + len(token_marker)
    end = body_text.find("&", start)
    token = body_text[start:end]
    assert token

    res = client.post("/v1/auth/verify", json={"token": token})
    assert res.status_code == 200
    body = res.json()
    assert body["email"] == "bob@example.com"
    # FastAPI test client persists cookies across calls.
    assert client.cookies.get("xv_session") is not None

    me = client.get("/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "bob@example.com"


def test_verify_rejects_unknown_token(client: TestClient) -> None:
    res = client.post("/v1/auth/verify", json={"token": "definitely-not-real"})
    assert res.status_code == 400
    assert res.headers["content-type"].startswith("application/problem+json")


def test_verify_rejects_reused_token(
    client: TestClient,
    fake_email: InMemoryEmailSender,
) -> None:
    client.post(
        "/v1/auth/request",
        json={"email": "carol@example.com", "locale": "uz"},
    )
    sent = fake_email.outbox[-1]
    token_marker = "?token="
    start = sent.text.find(token_marker) + len(token_marker)
    end = sent.text.find("&", start)
    token = sent.text[start:end]

    first = client.post("/v1/auth/verify", json={"token": token})
    assert first.status_code == 200
    second = client.post("/v1/auth/verify", json={"token": token})
    assert second.status_code == 400


def test_logout_clears_cookie(
    client: TestClient,
    fake_email: InMemoryEmailSender,
) -> None:
    client.post(
        "/v1/auth/request",
        json={"email": "dora@example.com", "locale": "en"},
    )
    sent = fake_email.outbox[-1]
    token_marker = "?token="
    start = sent.text.find(token_marker) + len(token_marker)
    end = sent.text.find("&", start)
    token = sent.text[start:end]
    client.post("/v1/auth/verify", json={"token": token})
    assert client.cookies.get("xv_session") is not None

    out = client.post("/v1/auth/logout")
    assert out.status_code == 200
    # Subsequent /me must be 401.
    me = client.get("/v1/auth/me")
    assert me.status_code == 401


def test_me_requires_auth(client: TestClient) -> None:
    res = client.get("/v1/auth/me")
    assert res.status_code == 401
    assert res.headers["content-type"].startswith("application/problem+json")


def test_request_link_rate_limited(client: TestClient) -> None:
    for _ in range(5):
        ok = client.post(
            "/v1/auth/request",
            json={"email": "eve@example.com", "locale": "en"},
            headers={"x-forwarded-for": "5.5.5.5"},
        )
        assert ok.status_code == 200
    overflow = client.post(
        "/v1/auth/request",
        json={"email": "eve@example.com", "locale": "en"},
        headers={"x-forwarded-for": "5.5.5.5"},
    )
    assert overflow.status_code == 429
