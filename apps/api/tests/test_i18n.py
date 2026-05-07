from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from xavfsizmi_api.core import i18n


def _app() -> FastAPI:
    app = FastAPI()

    @app.get("/echo-locale")
    async def echo(request: Request) -> dict[str, str]:
        return {"locale": i18n.negotiate(request)}

    return app


def test_query_string_wins() -> None:
    client = TestClient(_app())
    r = client.get(
        "/echo-locale?lang=ru",
        headers={"accept-language": "uz"},
        cookies={"xv_lang": "en"},
    )
    assert r.json()["locale"] == "ru"


def test_cookie_beats_header() -> None:
    client = TestClient(_app())
    r = client.get(
        "/echo-locale",
        headers={"accept-language": "en"},
        cookies={"xv_lang": "ru"},
    )
    assert r.json()["locale"] == "ru"


def test_falls_back_to_accept_language() -> None:
    client = TestClient(_app())
    r = client.get("/echo-locale", headers={"accept-language": "en-GB,fr;q=0.5"})
    assert r.json()["locale"] == "en"


def test_default_is_uz() -> None:
    client = TestClient(_app())
    r = client.get("/echo-locale")
    assert r.json()["locale"] == "uz"
