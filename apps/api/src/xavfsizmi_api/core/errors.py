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
    "auth.unauthorized.title": {
        "uz": "Avtorizatsiya talab qilinadi",
        "ru": "Требуется авторизация",
        "en": "Authentication required",
    },
    "auth.unauthorized.detail": {
        "uz": "Iltimos, hisobingizga kirib, qaytadan urinib ko'ring.",
        "ru": "Пожалуйста, войдите в учётную запись и повторите попытку.",
        "en": "Please sign in and try again.",
    },
    "auth.invalid_token.title": {
        "uz": "Havola yaroqsiz yoki muddati o'tgan",
        "ru": "Ссылка недействительна или просрочена",
        "en": "Link is invalid or expired",
    },
    "auth.invalid_token.detail": {
        "uz": "Havola muddati 15 daqiqa va u faqat bir marta ishlaydi. "
        "Iltimos, yangi havola so'rang.",
        "ru": "Ссылка действительна 15 минут и срабатывает один раз. Запросите новую ссылку.",
        "en": "The link is valid for 15 minutes and only works once. Please request a new one.",
    },
    "auth.api_key.missing.title": {
        "uz": "API kalit topilmadi",
        "ru": "API-ключ не найден",
        "en": "API key missing",
    },
    "auth.api_key.missing.detail": {
        "uz": "So'rovni `X-API-Key` sarlavhasi bilan yuboring.",
        "ru": "Передайте ключ в заголовке `X-API-Key`.",
        "en": "Send the key in the `X-API-Key` header.",
    },
    "auth.api_key.invalid.title": {
        "uz": "API kalit yaroqsiz",
        "ru": "Недействительный API-ключ",
        "en": "API key invalid",
    },
    "auth.api_key.invalid.detail": {
        "uz": "Kalit topilmadi yoki bekor qilingan.",
        "ru": "Ключ не найден или отозван.",
        "en": "The key was not found or has been revoked.",
    },
    "domain.invalid.title": {
        "uz": "Domen noto'g'ri",
        "ru": "Неверный домен",
        "en": "Invalid domain",
    },
    "domain.invalid.detail": {
        "uz": "Domen nomi to'g'ri formatda emas.",
        "ru": "Имя домена в неверном формате.",
        "en": "The domain name is not in a valid format.",
    },
    "domain.duplicate.title": {
        "uz": "Domen allaqachon ro'yxatdan o'tgan",
        "ru": "Домен уже зарегистрирован",
        "en": "Domain already registered",
    },
    "domain.not_found.title": {
        "uz": "Domen topilmadi",
        "ru": "Домен не найден",
        "en": "Domain not found",
    },
    "domain.verification_failed.title": {
        "uz": "Tasdiqlash muvaffaqiyatsiz",
        "ru": "Подтверждение не пройдено",
        "en": "Verification failed",
    },
    "notifications.invalid_token.title": {
        "uz": "Havola yaroqsiz",
        "ru": "Ссылка недействительна",
        "en": "Link is invalid",
    },
    "notifications.invalid_token.detail": {
        "uz": "Havola muddati o'tgan yoki noto'g'ri.",
        "ru": "Ссылка просрочена или некорректна.",
        "en": "The link has expired or is malformed.",
    },
    "admin.forbidden.title": {
        "uz": "Ruxsat yo'q",
        "ru": "Доступ запрещён",
        "en": "Forbidden",
    },
    "admin.forbidden.detail": {
        "uz": "Ushbu amal uchun administrator huquqi kerak.",
        "ru": "Для этого действия требуются права администратора.",
        "en": "Administrator privileges are required for this action.",
    },
    "billing.unavailable.title": {
        "uz": "To'lov tizimi sozlanmagan",
        "ru": "Платёжная система не настроена",
        "en": "Billing not configured",
    },
    "billing.unavailable.detail": {
        "uz": "Stripe API kaliti sozlanmagan, to'lov vaqtincha ishlamaydi.",
        "ru": "API-ключ Stripe не настроен, оплата временно недоступна.",
        "en": "The Stripe API key is not configured, billing is temporarily unavailable.",
    },
    "billing.invalid_tier.title": {
        "uz": "Tarif yaroqsiz",
        "ru": "Тариф недействителен",
        "en": "Invalid tier",
    },
    "billing.invalid_tier.detail": {
        "uz": "Bu tarif mavjud emas.",
        "ru": "Такого тарифа не существует.",
        "en": "That tier does not exist.",
    },
    "billing.no_customer.title": {
        "uz": "Mijoz topilmadi",
        "ru": "Клиент не найден",
        "en": "No billing customer",
    },
    "billing.no_customer.detail": {
        "uz": "Avval obuna sotib oling.",
        "ru": "Сначала оформите подписку.",
        "en": "Start a subscription before opening the billing portal.",
    },
    "billing.webhook.invalid.title": {
        "uz": "Webhook noto'g'ri",
        "ru": "Webhook некорректен",
        "en": "Invalid webhook",
    },
    "billing.webhook.invalid.detail": {
        "uz": "Stripe imzosi tasdiqlanmadi.",
        "ru": "Подпись Stripe не прошла проверку.",
        "en": "Stripe signature could not be verified.",
    },
    "admin.csv.empty.title": {
        "uz": "Fayl bo'sh",
        "ru": "Файл пуст",
        "en": "Empty file",
    },
    "admin.csv.empty.detail": {
        "uz": "Yuklangan CSV fayli bo'sh.",
        "ru": "Загруженный CSV-файл пуст.",
        "en": "The uploaded CSV file is empty.",
    },
    "admin.csv.invalid.title": {
        "uz": "CSV fayl yaroqsiz",
        "ru": "Неверный CSV-файл",
        "en": "Invalid CSV file",
    },
    "admin.csv.invalid.detail": {
        "uz": "CSV faylida `name` ustuni majburiy. Sarlavhalarni tekshiring.",
        "ru": "В CSV обязательна колонка `name`. Проверьте заголовки.",
        "en": "CSV must include a `name` column. Check the headers.",
    },
    "admin.dispatch.unknown_breach.title": {
        "uz": "Sızıntı topilmadi",
        "ru": "Утечка не найдена",
        "en": "Breach not found",
    },
    "admin.dispatch.unknown_breach.detail": {
        "uz": "Kataloglangan sızıntılar orasida bunday yozuv yo'q.",
        "ru": "В каталоге нет такой записи об утечке.",
        "en": "No cached breach matches that name.",
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
