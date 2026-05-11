"""Tests for the notifications subscription endpoint."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from xavfsizmi_api.config import get_settings


@pytest.fixture(autouse=True)
def _reset_settings() -> None:
    get_settings.cache_clear()


def test_subscribe_returns_pending_message(client: TestClient) -> None:
    res = client.post(
        "/v1/notifications/subscribe",
        json={"email": "alice@example.com", "locale": "uz"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "pending_confirmation"
    assert body["locale"] == "uz"
    assert "Tasdiqlash" in body["message"]


def test_subscribe_localises_message_for_ru(client: TestClient) -> None:
    res = client.post(
        "/v1/notifications/subscribe",
        json={"email": "ivan@example.com", "locale": "ru"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["locale"] == "ru"
    assert "ссылк" in body["message"].lower()


def test_subscribe_falls_back_to_default_locale_for_unknown(client: TestClient) -> None:
    res = client.post(
        "/v1/notifications/subscribe",
        json={"email": "x@example.com", "locale": "fr"},
    )
    # Pydantic rejects values outside the Literal at the schema layer.
    assert res.status_code == 422


def test_subscribe_rate_limited(client: TestClient) -> None:
    for _ in range(5):
        ok = client.post(
            "/v1/notifications/subscribe",
            json={"email": "a@example.com", "locale": "en"},
            headers={"x-forwarded-for": "9.9.9.9"},
        )
        assert ok.status_code == 200
    overflow = client.post(
        "/v1/notifications/subscribe",
        json={"email": "a@example.com", "locale": "en"},
        headers={"x-forwarded-for": "9.9.9.9"},
    )
    assert overflow.status_code == 429
    assert overflow.headers["content-type"].startswith("application/problem+json")


def _token_from_email(text: str) -> str:
    """Extract the first ``?token=…`` value from an email body."""
    start = text.find("?token=") + len("?token=")
    end = len(text)
    for ch in ("&", "\n", " ", "\r", '"'):
        idx = text.find(ch, start)
        if idx != -1 and idx < end:
            end = idx
    return text[start:end].rstrip("/")


def test_confirm_and_unsubscribe_roundtrip(client: TestClient, fake_email: object) -> None:
    res = client.post(
        "/v1/notifications/subscribe",
        json={"email": "bob@example.com", "locale": "en"},
    )
    assert res.status_code == 200
    sent = fake_email.outbox[-1]  # type: ignore[attr-defined]
    confirm_idx = sent.text.find("/confirm?token=")
    unsubscribe_idx = sent.text.find("/unsubscribe?token=")
    assert confirm_idx != -1 and unsubscribe_idx != -1
    confirm_token = _token_from_email(sent.text[confirm_idx:])
    unsubscribe_token = _token_from_email(sent.text[unsubscribe_idx:])

    bad = client.post("/v1/notifications/confirm", json={"token": "garbage"})
    assert bad.status_code == 400

    ok = client.post("/v1/notifications/confirm", json={"token": confirm_token})
    assert ok.status_code == 200
    assert ok.json()["status"] == "confirmed"

    # Resubscribe → already_confirmed.
    again = client.post(
        "/v1/notifications/subscribe",
        json={"email": "bob@example.com", "locale": "en"},
    )
    assert again.json()["status"] == "already_confirmed"

    uns = client.post("/v1/notifications/unsubscribe", json={"token": unsubscribe_token})
    assert uns.status_code == 200
    assert uns.json()["status"] == "unsubscribed"

    # Token now invalid.
    again2 = client.post("/v1/notifications/unsubscribe", json={"token": unsubscribe_token})
    assert again2.status_code == 400
