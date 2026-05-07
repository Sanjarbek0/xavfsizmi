"""End-to-end tests for the /v1/breaches endpoints with fake HIBP + Redis."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from .conftest import FakeHIBP, FakeRedis, FakeTurnstile


def _sample_breach() -> dict[str, Any]:
    return {
        "Name": "Adobe",
        "Title": "Adobe",
        "Domain": "adobe.com",
        "BreachDate": "2013-10-04",
        "PwnCount": 152_445_165,
        "IsVerified": True,
        "IsSensitive": False,
        "IsFabricated": False,
        "IsRetired": False,
        "IsSpamList": False,
        "Description": "In October 2013, Adobe suffered a breach.",
        "DataClasses": ["Email addresses", "Password hints"],
        "LogoPath": "/images/adobe.png",
    }


def test_account_returns_breaches(
    client: TestClient,
    fake_hibp: FakeHIBP,
) -> None:
    fake_hibp.breached_payload = [_sample_breach()]
    r = client.post("/v1/breaches/account", json={"email": "test@example.com"})
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "test@example.com"
    assert body["cached"] is False
    assert len(body["breaches"]) == 1
    b = body["breaches"][0]
    assert b["name"] == "Adobe"
    assert b["pwn_count"] == 152_445_165
    assert b["data_classes"] == ["Email addresses", "Password hints"]


def test_account_lookup_caches_response(
    client: TestClient,
    fake_hibp: FakeHIBP,
) -> None:
    fake_hibp.breached_payload = [_sample_breach()]
    first = client.post("/v1/breaches/account", json={"email": "test@example.com"})
    second = client.post("/v1/breaches/account", json={"email": "test@example.com"})
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["cached"] is False
    assert second.json()["cached"] is True
    # Upstream is hit only once thanks to cache.
    assert sum(1 for c in fake_hibp.calls if c[0] == "breached_account") == 1


def test_account_normalises_email_and_keys_cache_case_insensitive(
    client: TestClient,
    fake_hibp: FakeHIBP,
) -> None:
    fake_hibp.breached_payload = [_sample_breach()]
    a = client.post("/v1/breaches/account", json={"email": "Test@Example.com"})
    b = client.post("/v1/breaches/account", json={"email": "test@example.com"})
    assert a.status_code == 200 and b.status_code == 200
    assert a.json()["cached"] is False
    assert b.json()["cached"] is True
    assert a.json()["email"] == "test@example.com"


def test_account_rate_limited_after_threshold(
    client: TestClient,
    fake_hibp: FakeHIBP,
    fake_redis: FakeRedis,
) -> None:
    fake_hibp.breached_payload = []
    # _RL_ACCOUNT.limit_per_minute = 5; the 6th call within the same minute trips it.
    for i in range(5):
        r = client.post("/v1/breaches/account", json={"email": f"u{i}@example.com"})
        assert r.status_code == 200
    r = client.post("/v1/breaches/account", json={"email": "spam@example.com"})
    assert r.status_code == 429
    body = r.json()
    assert body["status"] == 429
    assert "title" in body
    fake_redis.reset()


def test_account_turnstile_failure_returns_403(
    client: TestClient,
    fake_hibp: FakeHIBP,
    fake_turnstile: FakeTurnstile,
    monkeypatch: Any,
) -> None:
    from xavfsizmi_api.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "turnstile_secret_key", "test-secret")
    fake_turnstile.ok = False

    r = client.post(
        "/v1/breaches/account",
        json={"email": "test@example.com", "turnstileToken": "bad"},
    )
    assert r.status_code == 403
    assert r.json()["status"] == 403


def test_list_all_breaches(
    client: TestClient,
    fake_hibp: FakeHIBP,
) -> None:
    fake_hibp.all_breaches_payload = [_sample_breach()]
    r = client.get("/v1/breaches")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["name"] == "Adobe"


def test_list_breaches_with_domain_filter(
    client: TestClient,
    fake_hibp: FakeHIBP,
) -> None:
    fake_hibp.all_breaches_payload = [_sample_breach()]
    r = client.get("/v1/breaches", params={"domain": "adobe.com"})
    assert r.status_code == 200
    domain_calls = [c for c in fake_hibp.calls if c[0] == "all_breaches"]
    assert domain_calls and domain_calls[0][1]["domain"] == "adobe.com"


def test_list_breaches_rejects_bad_domain(
    client: TestClient,
) -> None:
    r = client.get("/v1/breaches", params={"domain": "not a domain!!!"})
    assert r.status_code == 400


def test_get_breach_by_name(
    client: TestClient,
    fake_hibp: FakeHIBP,
) -> None:
    fake_hibp.breach_payload["Adobe"] = _sample_breach()
    r = client.get("/v1/breaches/Adobe")
    assert r.status_code == 200
    assert r.json()["name"] == "Adobe"


def test_get_breach_404(
    client: TestClient,
) -> None:
    r = client.get("/v1/breaches/Nope123")
    assert r.status_code == 404
    assert r.json()["status"] == 404


def test_paste_lookup(
    client: TestClient,
    fake_hibp: FakeHIBP,
) -> None:
    fake_hibp.pastes_payload = [
        {
            "Source": "Pastebin",
            "Id": "abc123",
            "Title": "Sample",
            "Date": "2024-01-01T00:00:00Z",
            "EmailCount": 10,
        }
    ]
    r = client.post("/v1/breaches/paste", json={"email": "test@example.com"})
    assert r.status_code == 200
    body = r.json()
    assert len(body["pastes"]) == 1
    assert body["pastes"][0]["source"] == "Pastebin"
