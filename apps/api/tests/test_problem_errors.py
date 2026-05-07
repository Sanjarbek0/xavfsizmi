from fastapi.testclient import TestClient

from xavfsizmi_api.main import app


def test_404_is_problem_json_uz_by_default() -> None:
    client = TestClient(app)
    r = client.get("/this-does-not-exist")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert body["status"] == 404
    # default locale is uz
    assert body["title"] == "Topilmadi"


def test_404_is_localised_to_ru_via_cookie() -> None:
    client = TestClient(app)
    r = client.get("/this-does-not-exist", cookies={"xv_lang": "ru"})
    assert r.status_code == 404
    assert r.json()["title"] == "Не найдено"


def test_404_is_localised_to_en_via_query() -> None:
    client = TestClient(app)
    r = client.get("/this-does-not-exist?lang=en")
    assert r.status_code == 404
    assert r.json()["title"] == "Not found"
