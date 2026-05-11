"""Admin role enforcement + admin endpoints."""

from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from xavfsizmi_api.config import get_settings
from xavfsizmi_api.db.models import User

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


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    user = User(email="admin@example.com", is_admin=True)
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.fixture(autouse=True)
def _reset_settings() -> None:
    get_settings.cache_clear()


def test_admin_endpoints_reject_non_admin(
    client: TestClient, fake_email: InMemoryEmailSender
) -> None:
    _login(client, "regular@example.com", fake_email)
    for path in (
        "/v1/admin/metrics",
        "/v1/admin/users",
        "/v1/admin/audit",
        "/v1/admin/breaches",
    ):
        res = client.get(path)
        assert res.status_code == 403, path


def test_admin_metrics_and_users_listing(
    client: TestClient,
    admin_user: User,
    fake_email: InMemoryEmailSender,
) -> None:
    _login(client, admin_user.email, fake_email)
    metrics = client.get("/v1/admin/metrics")
    assert metrics.status_code == 200
    payload = metrics.json()
    assert payload["user_count"] >= 1

    users = client.get("/v1/admin/users").json()
    emails = {row["email"] for row in users["users"]}
    assert admin_user.email in emails


def test_admin_block_user_toggles_state(
    client: TestClient,
    admin_user: User,
    fake_email: InMemoryEmailSender,
) -> None:
    _login(client, "victim@example.com", fake_email)
    client.post("/v1/auth/logout")
    _login(client, admin_user.email, fake_email)

    users = client.get("/v1/admin/users").json()["users"]
    victim = next(u for u in users if u["email"] == "victim@example.com")

    res = client.post(f"/v1/admin/users/{victim['id']}/block", json={"blocked": True})
    assert res.status_code == 200
    assert res.json()["is_blocked"] is True

    res = client.post(f"/v1/admin/users/{victim['id']}/block", json={"blocked": False})
    assert res.json()["is_blocked"] is False


def test_admin_breach_upsert(
    client: TestClient,
    admin_user: User,
    fake_email: InMemoryEmailSender,
) -> None:
    _login(client, admin_user.email, fake_email)
    payload = {
        "name": "TestLeak",
        "title": "Test Leak",
        "domain": "test.example",
        "breach_date": "2026-05-01",
        "pwn_count": 1234,
        "is_verified": True,
        "is_sensitive": False,
        "description": "A test breach.",
        "data_classes": ["Emails", "Passwords"],
    }
    res = client.post("/v1/admin/breaches", json=payload)
    assert res.status_code == 200
    assert res.json()["title"] == "Test Leak"

    listing = client.get("/v1/admin/breaches").json()
    names = {b["name"] for b in listing["breaches"]}
    assert "TestLeak" in names


def test_admin_emails_setting_elevates_user_on_login(
    client: TestClient,
    fake_email: InMemoryEmailSender,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ADMIN_EMAILS", "newadmin@example.com")
    get_settings.cache_clear()
    try:
        _login(client, "newadmin@example.com", fake_email)
        res = client.get("/v1/auth/me").json()
        assert res["is_admin"] is True
    finally:
        get_settings.cache_clear()
