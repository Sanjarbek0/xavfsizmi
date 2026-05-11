"""Tests for the Phase 8 admin features: CSV import, dispatch, stats."""

from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta

import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from xavfsizmi_api.db.models import (
    ApiKey,
    BreachCache,
    NotificationSubscription,
    User,
)

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


# ---------------------------------------------------------------------------
# CSV upload
# ---------------------------------------------------------------------------


def test_csv_upload_inserts_new_breaches(
    client: TestClient,
    admin_user: User,
    fake_email: InMemoryEmailSender,
) -> None:
    _login(client, admin_user.email, fake_email)
    csv_body = (
        "name,title,domain,breach_date,pwn_count,is_verified,is_sensitive,description,data_classes\n"
        "FreshLeak,Fresh Leak,fresh.example,2026-04-01,1000,true,false,Recent leak,Emails;Passwords\n"
        "AnotherOne,Another One,another.example,2026-04-02,250,no,yes,Sensitive,Emails\n"
    )
    res = client.post(
        "/v1/admin/breaches/upload",
        files={"file": ("breaches.csv", csv_body, "text/csv")},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["inserted"] == 2
    assert body["updated"] == 0
    assert set(body["inserted_names"]) == {"FreshLeak", "AnotherOne"}
    assert body["dry_run"] is False

    listing = client.get("/v1/admin/breaches").json()
    names = {b["name"] for b in listing["breaches"]}
    assert {"FreshLeak", "AnotherOne"} <= names


def test_csv_upload_updates_existing_partial_fields(
    client: TestClient,
    admin_user: User,
    fake_email: InMemoryEmailSender,
    db_session: AsyncSession,
) -> None:
    _login(client, admin_user.email, fake_email)
    # Seed an existing row
    res = client.post(
        "/v1/admin/breaches",
        json={
            "name": "Existing",
            "title": "Existing Title",
            "domain": "existing.example",
            "breach_date": "2026-01-01",
            "pwn_count": 10,
            "is_verified": True,
            "is_sensitive": False,
            "description": "Old description",
            "data_classes": ["Emails"],
        },
    )
    assert res.status_code == 200

    # CSV only updates pwn_count + description; other fields must survive.
    csv_body = "name,pwn_count,description\nExisting,9999,Updated description\n"
    res = client.post(
        "/v1/admin/breaches/upload",
        files={"file": ("upd.csv", csv_body, "text/csv")},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["updated"] == 1
    assert body["inserted"] == 0

    listing = client.get("/v1/admin/breaches").json()
    row = next(b for b in listing["breaches"] if b["name"] == "Existing")
    assert row["pwn_count"] == 9999
    assert row["description"] == "Updated description"
    # untouched
    assert row["title"] == "Existing Title"
    assert row["domain"] == "existing.example"


def test_csv_upload_rejects_missing_name_column(
    client: TestClient,
    admin_user: User,
    fake_email: InMemoryEmailSender,
) -> None:
    _login(client, admin_user.email, fake_email)
    csv_body = "title,domain\nfoo,bar.example\n"
    res = client.post(
        "/v1/admin/breaches/upload",
        files={"file": ("bad.csv", csv_body, "text/csv")},
    )
    assert res.status_code == 400, res.text
    payload = res.json()
    # extras propagated through ProblemError
    assert "headers" in payload
    assert any(
        e["message"].startswith("missing_required_column") for e in payload.get("errors", [])
    )


def test_csv_upload_dry_run_does_not_write(
    client: TestClient,
    admin_user: User,
    fake_email: InMemoryEmailSender,
) -> None:
    _login(client, admin_user.email, fake_email)
    csv_body = "name,title\nDryOnly,Dry Only\n"
    res = client.post(
        "/v1/admin/breaches/upload?dry_run=true",
        files={"file": ("dry.csv", csv_body, "text/csv")},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["dry_run"] is True
    assert body["inserted"] == 1

    listing = client.get("/v1/admin/breaches").json()
    names = {b["name"] for b in listing["breaches"]}
    assert "DryOnly" not in names


def test_csv_upload_rejects_empty_file(
    client: TestClient,
    admin_user: User,
    fake_email: InMemoryEmailSender,
) -> None:
    _login(client, admin_user.email, fake_email)
    res = client.post(
        "/v1/admin/breaches/upload",
        files={"file": ("empty.csv", io.BytesIO(b""), "text/csv")},
    )
    assert res.status_code == 400


def test_csv_upload_requires_admin(
    client: TestClient,
    fake_email: InMemoryEmailSender,
) -> None:
    _login(client, "regular@example.com", fake_email)
    res = client.post(
        "/v1/admin/breaches/upload",
        files={"file": ("x.csv", "name\nA\n", "text/csv")},
    )
    assert res.status_code == 403


# ---------------------------------------------------------------------------
# Manual dispatch
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def seeded_dispatch(db_session: AsyncSession) -> dict[str, object]:
    breach = BreachCache(
        name="Adobe",
        title="Adobe",
        domain="adobe.com",
        breach_date="2013-10-04",
        pwn_count=152_000_000,
    )
    db_session.add(breach)

    confirmed = NotificationSubscription(
        email="alice@example.com",
        locale="en",
        confirmed_at=datetime.now(UTC),
        unsubscribe_token_hash="alice-hash",
    )
    pending = NotificationSubscription(
        email="bob@example.com",
        locale="ru",
        unsubscribe_token_hash="bob-hash",
    )
    second = NotificationSubscription(
        email="charlie@example.com",
        locale="uz",
        confirmed_at=datetime.now(UTC),
        unsubscribe_token_hash="charlie-hash",
    )
    db_session.add_all([confirmed, pending, second])
    await db_session.commit()
    return {"breach": breach, "confirmed": confirmed, "pending": pending, "second": second}


def test_dispatch_sends_to_confirmed_only(
    client: TestClient,
    admin_user: User,
    fake_email: InMemoryEmailSender,
    seeded_dispatch: dict[str, object],
) -> None:
    _login(client, admin_user.email, fake_email)
    fake_email.reset()

    res = client.post(
        "/v1/admin/notifications/dispatch",
        json={"breach_name": "Adobe"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["sent"] == 2
    assert body["failed"] == 0
    assert body["total_subscribers"] == 2
    recipients = {r["email"] for r in body["recipients"] if r["sent"]}
    assert recipients == {"alice@example.com", "charlie@example.com"}

    sent_to = {msg.to for msg in fake_email.outbox}
    assert sent_to == {"alice@example.com", "charlie@example.com"}
    assert "bob@example.com" not in sent_to


def test_dispatch_dry_run_emits_no_emails(
    client: TestClient,
    admin_user: User,
    fake_email: InMemoryEmailSender,
    seeded_dispatch: dict[str, object],
) -> None:
    _login(client, admin_user.email, fake_email)
    fake_email.reset()

    res = client.post(
        "/v1/admin/notifications/dispatch",
        json={"breach_name": "Adobe", "dry_run": True},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["dry_run"] is True
    assert body["sent"] == 0
    assert body["skipped"] == 2
    assert body["total_subscribers"] == 2
    assert fake_email.outbox == []


def test_dispatch_404_when_breach_unknown(
    client: TestClient,
    admin_user: User,
    fake_email: InMemoryEmailSender,
) -> None:
    _login(client, admin_user.email, fake_email)
    res = client.post(
        "/v1/admin/notifications/dispatch",
        json={"breach_name": "NonExistent"},
    )
    assert res.status_code == 404


def test_dispatch_requires_admin(
    client: TestClient,
    fake_email: InMemoryEmailSender,
) -> None:
    _login(client, "regular@example.com", fake_email)
    res = client.post(
        "/v1/admin/notifications/dispatch",
        json={"breach_name": "Adobe"},
    )
    assert res.status_code == 403


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def stats_admin(db_session: AsyncSession) -> User:
    admin = User(email="stats-admin@example.com", is_admin=True)
    db_session.add(admin)

    db_session.add(User(email="u1@example.com"))
    db_session.add(User(email="u2@example.com", is_blocked=True))
    pro_user = User(
        email="pro@example.com",
        subscription_tier="pro",
        subscription_status="active",
    )
    db_session.add(pro_user)
    await db_session.flush()

    db_session.add(
        ApiKey(
            user_id=pro_user.id,
            key_prefix="aaaa",
            key_hash="hashpro",
            tier="pro",
        )
    )
    db_session.add(
        ApiKey(
            user_id=pro_user.id,
            key_prefix="bbbb",
            key_hash="hashpro2",
            tier="free",
        )
    )
    db_session.add(
        ApiKey(
            user_id=pro_user.id,
            key_prefix="cccc",
            key_hash="hashrev",
            tier="high_rpm",
            is_revoked=True,
        )
    )

    now = datetime.now(UTC)
    db_session.add(
        BreachCache(
            name="Big",
            title="Big",
            pwn_count=1_000_000,
            is_verified=True,
            is_sensitive=False,
            refreshed_at=now,
        )
    )
    db_session.add(
        BreachCache(
            name="Small",
            title="Small",
            pwn_count=50,
            is_verified=True,
            is_sensitive=True,
            refreshed_at=now - timedelta(days=2),
        )
    )

    db_session.add(
        NotificationSubscription(
            email="confirmed@example.com",
            locale="en",
            confirmed_at=now,
            unsubscribe_token_hash="conf",
        )
    )
    db_session.add(
        NotificationSubscription(
            email="pending@example.com",
            locale="en",
            unsubscribe_token_hash="pend",
        )
    )
    await db_session.commit()
    return admin


def test_user_stats_endpoint(
    client: TestClient,
    stats_admin: User,
    fake_email: InMemoryEmailSender,
) -> None:
    _login(client, stats_admin.email, fake_email)

    res = client.get("/v1/admin/stats/users")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["total_users"] >= 4
    assert body["blocked_users"] >= 1
    assert body["admin_users"] >= 1
    assert body["active_subscribers"] >= 1
    assert body["pending_subscribers"] >= 1
    assert body["by_tier"].get("pro", 0) >= 1
    assert body["by_tier"].get("free", 0) >= 1
    # Revoked keys should not show up
    assert body["by_tier"].get("high_rpm", 0) == 0
    assert len(body["signups_last_30_days"]) == 30


def test_breach_stats_endpoint(
    client: TestClient,
    stats_admin: User,
    fake_email: InMemoryEmailSender,
) -> None:
    _login(client, stats_admin.email, fake_email)

    res = client.get("/v1/admin/stats/breaches?top_n=5")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["total_breaches"] >= 2
    assert body["sensitive_breaches"] >= 1
    assert body["verified_breaches"] >= 2
    assert body["total_pwn_count"] >= 1_000_050
    assert len(body["top_by_pwn_count"]) <= 5
    assert body["top_by_pwn_count"][0]["name"] == "Big"
    assert len(body["breaches_added_last_30_days"]) == 30


def test_stats_requires_admin(
    client: TestClient,
    fake_email: InMemoryEmailSender,
) -> None:
    _login(client, "regular@example.com", fake_email)
    for path in ("/v1/admin/stats/users", "/v1/admin/stats/breaches"):
        res = client.get(path)
        assert res.status_code == 403, path
