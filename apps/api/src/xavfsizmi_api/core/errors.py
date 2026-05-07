"""RFC 7807 problem+json error handlers, with localised messages."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from . import i18n

PROBLEM_TYPE = "https://xavfsizmi.example/problems"

# Locale-keyed messages for raise-from-anywhere ProblemError instances. Each
# entry is `key -> {locale: text}` so callers raise by key rather than ship
# untranslated strings into responses.
_PROBLEM_MESSAGES: dict[str, dict[i18n.Locale, str]] = {
    "rate_limited.title": {
        "uz": "Juda ko'p so'rov",
        "ru": "Слишком много запросов",
        "en": "Too many requests",
    },
    "rate_limited.detail": {
        "uz": "Iltimos, biroz kutib turing va keyin qayta urinib ko'ring.",
        "ru": "Пожалуйста, подождите немного и попробуйте снова.",
        "en": "Please wait a moment and try again.",
    },
    "hibp.upstream_error.title": {
        "uz": "Ma'lumot manbai bilan aloqa muvaffaqiyatsiz",
        "ru": "Не удалось связаться с источником данных",
        "en": "Upstream data source unavailable",
    },
    "hibp.upstream_error.detail": {
        "uz": "Tashqi ma'lumot bazasi vaqtinchalik javob bermayapti. Birozdan keyin urinib ko'ring.",
        "ru": "Внешняя база данных временно недоступна. Попробуйте чуть позже.",
        "en": "The external breach database is temporarily unavailable. Try again shortly.",
    },
    "turnstile.failed.title": {
        "uz": "Insonlik tekshiruvi muvaffaqiyatsiz",
        "ru": "Проверка человека не пройдена",
        "en": "Human check failed",
    },
    "turnstile.failed.detail": {
        "uz": "Iltimos, sahifani yangilang va qayta urinib ko'ring.",
        "ru": "Пожалуйста, обновите страницу и попробуйте снова.",
        "en": "Please refresh the page and try again.",
    },
    "breach.not_found.title": {
        "uz": "Sızıntı topilmadi",
        "ru": "Утечка не найдена",
        "en": "Breach not found",
    },
    "validation.bad_email.detail": {
        "uz": "Email manzili noto'g'ri.",
        "ru": "Неверный адрес электронной почты.",
        "en": "Email address is invalid.",
    },
}


def _localise(key: str | None, locale: i18n.Locale) -> str | None:
    if key is None:
        return None
    bundle = _PROBLEM_MESSAGES.get(key)
    if bundle is None:
        return key  # passthrough so dev typos remain visible
    return bundle.get(locale) or bundle.get("en")


class ProblemError(Exception):
    """Structured exception that maps cleanly onto an RFC 7807 problem+json response.

    Routers raise this with locale-keyed message keys; the global handler
    resolves them against the request's negotiated locale.
    """

    def __init__(
        self,
        *,
        status: int,
        type_: str | None = None,
        title_key: str | None = None,
        detail_key: str | None = None,
        extras: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(title_key or detail_key or f"problem-{status}")
        self.status = status
        self.type_ = type_ or f"{PROBLEM_TYPE}/{status}"
        self.title_key = title_key
        self.detail_key = detail_key
        self.extras = extras or {}


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


def _problem(
    status_code: int,
    locale: i18n.Locale,
    detail: str | None = None,
    *,
    type_: str | None = None,
    title: str | None = None,
    extras: dict[str, Any] | None = None,
) -> JSONResponse:
    if title is None:
        title = _TITLES.get(locale, _TITLES["en"]).get(status_code) or _TITLES["en"].get(
            status_code, "Error"
        )
    body: dict[str, Any] = {
        "type": type_ or f"{PROBLEM_TYPE}/{status_code}",
        "title": title,
        "status": status_code,
    }
    if detail:
        body["detail"] = detail
    if extras:
        body.update(extras)
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

    @app.exception_handler(ProblemError)
    async def _problem_error(request: Request, exc: ProblemError) -> JSONResponse:
        locale = i18n.negotiate(request)
        return _problem(
            exc.status,
            locale,
            detail=_localise(exc.detail_key, locale),
            type_=exc.type_,
            title=_localise(exc.title_key, locale),
            extras=exc.extras,
        )
