"""Tests for the request-observability middleware + ``/metrics`` endpoint."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_request_id_is_echoed_back(client: TestClient) -> None:
    """When the client supplies an X-Request-ID, the server keeps it intact."""
    r = client.get("/healthz", headers={"X-Request-ID": "abc-123"})
    assert r.status_code == 200
    assert r.headers["x-request-id"] == "abc-123"


def test_request_id_is_generated_when_missing(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    # 32-char hex (uuid4 hex form).
    assert len(r.headers["x-request-id"]) == 32
    int(r.headers["x-request-id"], 16)  # parseable as hex


def test_metrics_endpoint_exposes_request_counter(client: TestClient) -> None:
    """Hit a known route, then confirm /metrics has counted that request."""
    client.get("/healthz")
    client.get("/healthz")

    r = client.get("/metrics")
    assert r.status_code == 200
    body = r.text
    # Counter names + the route label format we expect.
    assert "xavfsizmi_http_requests_total" in body
    assert 'route="/healthz"' in body
    # And the latency histogram is exposed.
    assert "xavfsizmi_http_request_duration_seconds_bucket" in body


def test_metrics_endpoint_requires_token_when_configured(client: TestClient) -> None:
    """A configured METRICS_TOKEN must be supplied as a Bearer token."""
    from xavfsizmi_api.config import get_settings

    settings = get_settings()
    settings.metrics_token = "scrape-only-shh"
    try:
        r = client.get("/metrics")
        assert r.status_code == 401

        r2 = client.get("/metrics", headers={"Authorization": "Bearer scrape-only-shh"})
        assert r2.status_code == 200
    finally:
        settings.metrics_token = ""


def test_metrics_can_be_disabled(client: TestClient) -> None:
    """``METRICS_ENABLED=0`` makes /metrics 404."""
    from xavfsizmi_api.config import get_settings

    settings = get_settings()
    settings.metrics_enabled = False
    try:
        r = client.get("/metrics")
        assert r.status_code == 404
    finally:
        settings.metrics_enabled = True
