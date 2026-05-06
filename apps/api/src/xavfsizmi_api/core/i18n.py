"""Locale negotiation for API responses."""

from __future__ import annotations

from typing import Final, Literal

from fastapi import Request

Locale = Literal["uz", "ru", "en"]
SUPPORTED: Final[tuple[Locale, ...]] = ("uz", "ru", "en")
DEFAULT: Final[Locale] = "uz"


def _coerce(value: str | None) -> Locale | None:
    if value is None:
        return None
    if value in SUPPORTED:
        return value
    return None


def negotiate(request: Request) -> Locale:
    """Pick a locale from ?lang=, the xv_lang cookie, or Accept-Language."""
    qs = _coerce(request.query_params.get("lang"))
    if qs is not None:
        return qs

    cookie = _coerce(request.cookies.get("xv_lang"))
    if cookie is not None:
        return cookie

    header = request.headers.get("accept-language", "")
    for chunk in header.split(","):
        tag = chunk.split(";")[0].strip().lower().split("-")[0]
        coerced = _coerce(tag)
        if coerced is not None:
            return coerced

    return DEFAULT
