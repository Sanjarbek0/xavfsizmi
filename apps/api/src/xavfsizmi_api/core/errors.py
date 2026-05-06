"""RFC 7807 problem+json error handlers, with localised messages."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from . import i18n

PROBLEM_TYPE = "https://xavfsizmi.example/problems"

_TITLES: dict[i18n.Locale, dict[int, str]] = {
    "uz": {
        400: "Noto'g'ri so'rov",
        401: "Avtorizatsiya talab qilinadi",
        403: "Ruxsat berilmagan",
        404: "Topilmadi",
        409: "Ziddiyat",
        422: "So'rov tekshiruvdan o'tmadi",
        429: "Juda ko'p so'rov",
        500: "Server xatosi",
    },
    "ru": {
        400: "Неверный запрос",
        401: "Требуется авторизация",
        403: "Доступ запрещён",
        404: "Не найдено",
        409: "Конфликт",
        422: "Ошибка валидации",
        429: "Слишком много запросов",
        500: "Ошибка сервера",
    },
    "en": {
        400: "Bad request",
        401: "Authentication required",
        403: "Forbidden",
        404: "Not found",
        409: "Conflict",
        422: "Validation failed",
        429: "Too many requests",
        500: "Internal server error",
    },
}


def _problem(status_code: int, locale: i18n.Locale, detail: str | None = None) -> JSONResponse:
    title = _TITLES.get(locale, _TITLES["en"]).get(status_code) or _TITLES["en"].get(
        status_code, "Error"
    )
    body: dict[str, Any] = {
        "type": f"{PROBLEM_TYPE}/{status_code}",
        "title": title,
        "status": status_code,
    }
    if detail:
        body["detail"] = detail
    return JSONResponse(
        status_code=status_code,
        content=body,
        media_type="application/problem+json",
    )


def install_problem_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def _http(request: Request, exc: HTTPException) -> JSONResponse:
        locale = i18n.negotiate(request)
        detail = exc.detail if isinstance(exc.detail, str) else None
        return _problem(exc.status_code, locale, detail)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        locale = i18n.negotiate(request)
        first = exc.errors()[0] if exc.errors() else None
        detail = f"{'.'.join(str(p) for p in first['loc'])}: {first['msg']}" if first else None
        return _problem(status.HTTP_422_UNPROCESSABLE_ENTITY, locale, detail)
