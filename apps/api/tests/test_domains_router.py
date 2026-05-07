"""Domain registration + verification tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from xavfsizmi_api.config import get_settings

from .conftest import FakeDomainVerifier, InMemoryEmailSender, VerificationResult


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


def test_register_dns_txt_then_verify_success(
    client: TestClient,
    fake_email: InMemoryEmailSender,
    fake_verifier: FakeDomainVerifier,
) -> None:
    _login(client, "owner@example.com", fake_email)

    create = client.post(
        "/v1/account/domains",
        json={"name": "example.com", "verification_method": "dns_txt", "locale": "en"},
    )
    assert create.status_code == 201
    domain = create.json()["domain"]
    assert domain["name"] == "example.com"
    assert domain["verification_method"] == "dns_txt"
    assert domain["instructions"]["host"] == "_xavfsizmi.example.com"
    assert domain["instructions"]["type"] == "TXT"
    assert domain["verification_token"]

    fake_verifier.dns_results["example.com"] = VerificationResult(True)
    verify = client.post(
        f"/v1/account/domains/{domain['id']}/verify",
        json={},
    )
    assert verify.status_code == 200
    body = verify.json()
    assert body["status"] == "verified"
    assert body["domain"]["verified_at"] is not None


def test_register_email_method_sends_token_email(
    client: TestClient,
    fake_email: InMemoryEmailSender,
) -> None:
    _login(client, "domain-owner@example.com", fake_email)
    pre_count = len(fake_email.outbox)
    res = client.post(
        "/v1/account/domains",
        json={
            "name": "shop.example",
            "verification_method": "email",
            "locale": "uz",
            "notify_email": "admin@shop.example",
        },
    )
    assert res.status_code == 201
    assert len(fake_email.outbox) == pre_count + 1
    sent = fake_email.outbox[-1]
    assert sent.to == "admin@shop.example"
    assert "shop.example" in sent.subject


def test_email_verification_requires_matching_token(
    client: TestClient,
    fake_email: InMemoryEmailSender,
) -> None:
    _login(client, "ev@example.com", fake_email)
    res = client.post(
        "/v1/account/domains",
        json={
            "name": "ev.example",
            "verification_method": "email",
            "locale": "en",
            "notify_email": "admin@ev.example",
        },
    )
    assert res.status_code == 201
    domain = res.json()["domain"]
    real_token = domain["verification_token"]

    bad = client.post(
        f"/v1/account/domains/{domain['id']}/verify",
        json={"submitted_token": "wrong"},
    )
    assert bad.status_code == 200
    assert bad.json()["status"] == "failed"

    good = client.post(
        f"/v1/account/domains/{domain['id']}/verify",
        json={"submitted_token": real_token},
    )
    assert good.status_code == 200
    assert good.json()["status"] == "verified"


def test_meta_tag_verification_uses_verifier(
    client: TestClient,
    fake_email: InMemoryEmailSender,
    fake_verifier: FakeDomainVerifier,
) -> None:
    _login(client, "mt@example.com", fake_email)
    res = client.post(
        "/v1/account/domains",
        json={"name": "meta.example", "verification_method": "meta_tag", "locale": "en"},
    )
    domain = res.json()["domain"]
    fake_verifier.meta_results["meta.example"] = VerificationResult(True)
    out = client.post(f"/v1/account/domains/{domain['id']}/verify", json={})
    assert out.json()["status"] == "verified"


def test_register_invalid_domain_is_rejected(
    client: TestClient,
    fake_email: InMemoryEmailSender,
) -> None:
    _login(client, "bd@example.com", fake_email)
    res = client.post(
        "/v1/account/domains",
        json={"name": "not_a_domain", "verification_method": "dns_txt", "locale": "en"},
    )
    assert res.status_code == 422
    assert res.headers["content-type"].startswith("application/problem+json")


def test_register_duplicate_domain_returns_409(
    client: TestClient,
    fake_email: InMemoryEmailSender,
) -> None:
    _login(client, "dup@example.com", fake_email)
    payload = {"name": "dupe.example", "verification_method": "dns_txt", "locale": "en"}
    first = client.post("/v1/account/domains", json=payload)
    assert first.status_code == 201
    second = client.post("/v1/account/domains", json=payload)
    assert second.status_code == 409


def test_delete_domain(
    client: TestClient,
    fake_email: InMemoryEmailSender,
) -> None:
    _login(client, "del@example.com", fake_email)
    res = client.post(
        "/v1/account/domains",
        json={"name": "rm.example", "verification_method": "dns_txt", "locale": "en"},
    )
    domain_id = res.json()["domain"]["id"]
    out = client.delete(f"/v1/account/domains/{domain_id}")
    assert out.status_code == 204
    listed = client.get("/v1/account/domains").json()
    assert all(d["id"] != domain_id for d in listed["items"])


def test_domain_routes_require_auth(client: TestClient) -> None:
    assert client.get("/v1/account/domains").status_code == 401
    assert (
        client.post(
            "/v1/account/domains",
            json={"name": "x.example", "verification_method": "dns_txt", "locale": "en"},
        ).status_code
        == 401
    )
