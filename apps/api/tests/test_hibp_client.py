import httpx
import pytest

from xavfsizmi_api.config import Settings
from xavfsizmi_api.services.hibp_client import HIBPClient, HIBPError


@pytest.fixture
def settings() -> Settings:
    return Settings(
        hibp_api_key="x" * 32,
        hibp_base_url="https://hibp.test/api/v3",
        hibp_user_agent="xavfsizmi-test",
    )


async def test_breached_account_returns_list(settings: Settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.raw_path == (
            b"/api/v3/breachedaccount/foo%40bar.com?truncateResponse=false&IncludeUnverified=true"
        )
        assert request.headers["hibp-api-key"] == "x" * 32
        assert request.headers["user-agent"] == "xavfsizmi-test"
        return httpx.Response(200, json=[{"Name": "Adobe"}])

    client = HIBPClient(settings, httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    try:
        out = await client.breached_account("foo@bar.com")
    finally:
        await client.aclose()
    assert out == [{"Name": "Adobe"}]


async def test_breached_account_404_is_empty(settings: Settings) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    client = HIBPClient(settings, httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    try:
        out = await client.breached_account("nobody@example.com")
    finally:
        await client.aclose()
    assert out == []


async def test_propagates_5xx_as_hibp_error(settings: Settings) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"message": "upstream down"})

    client = HIBPClient(settings, httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    try:
        with pytest.raises(HIBPError) as ei:
            await client.breached_account("foo@bar.com")
    finally:
        await client.aclose()
    assert ei.value.status == 503


async def test_missing_api_key_raises() -> None:
    s = Settings(hibp_api_key="", hibp_base_url="https://hibp.test/api/v3")
    client = HIBPClient(s)
    try:
        with pytest.raises(HIBPError):
            await client.breached_account("foo@bar.com")
    finally:
        await client.aclose()
