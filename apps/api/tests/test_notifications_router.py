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
