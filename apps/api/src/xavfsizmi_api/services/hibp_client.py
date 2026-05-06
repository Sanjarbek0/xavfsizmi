"""Thin async client for the HIBP v3 API."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from ..config import Settings, get_settings


class HIBPError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class HIBPClient:
    """Async wrapper around the HIBP v3 endpoints we use.

    All methods are idempotent GETs; auth is via the `hibp-api-key` header
    on every request. The free Pwned Passwords range endpoint is handled
    separately by `routers/passwords.py` (and primarily by the Worker).
    """

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._client = client or httpx.AsyncClient(timeout=10.0)

    @classmethod
    def from_settings(cls) -> HIBPClient:
        return cls(get_settings())

    async def aclose(self) -> None:
        await self._client.aclose()

    async def breached_account(
        self,
        email: str,
        *,
        truncate_response: bool = False,
        include_unverified: bool = True,
    ) -> list[dict[str, Any]]:
        params: dict[str, str] = {
            "truncateResponse": "true" if truncate_response else "false",
            "IncludeUnverified": "true" if include_unverified else "false",
        }
        url = f"{self._settings.hibp_base_url}/breachedaccount/{quote(email, safe='')}"
        return await self._get_list(url, params=params)

    async def all_breaches(self, *, domain: str | None = None) -> list[dict[str, Any]]:
        params: dict[str, str] = {}
        if domain:
            params["Domain"] = domain
        url = f"{self._settings.hibp_base_url}/breaches"
        return await self._get_list(url, params=params)

    async def breach(self, name: str) -> dict[str, Any] | None:
        url = f"{self._settings.hibp_base_url}/breach/{quote(name, safe='')}"
        try:
            return await self._get_json(url)
        except HIBPError as e:
            if e.status == 404:
                return None
            raise

    async def pastes(self, email: str) -> list[dict[str, Any]]:
        url = f"{self._settings.hibp_base_url}/pasteaccount/{quote(email, safe='')}"
        return await self._get_list(url)

    # ---- low-level helpers ----------------------------------------------

    def _headers(self) -> dict[str, str]:
        if not self._settings.hibp_api_key:
            raise HIBPError("HIBP_API_KEY is not configured")
        return {
            "hibp-api-key": self._settings.hibp_api_key,
            "User-Agent": self._settings.hibp_user_agent,
            "Accept": "application/json",
        }

    async def _get_list(
        self, url: str, *, params: dict[str, str] | None = None
    ) -> list[dict[str, Any]]:
        r = await self._client.get(url, headers=self._headers(), params=params)
        if r.status_code == 404:
            return []
        if r.status_code >= 400:
            raise HIBPError(_message(r), status=r.status_code)
        data = r.json()
        if not isinstance(data, list):
            raise HIBPError(f"unexpected payload from {url}", status=r.status_code)
        return data

    async def _get_json(self, url: str) -> dict[str, Any]:
        r = await self._client.get(url, headers=self._headers())
        if r.status_code >= 400:
            raise HIBPError(_message(r), status=r.status_code)
        data = r.json()
        if not isinstance(data, dict):
            raise HIBPError(f"unexpected payload from {url}", status=r.status_code)
        return data


def _message(r: httpx.Response) -> str:
    try:
        body = r.json()
        if isinstance(body, dict) and "message" in body:
            return str(body["message"])
    except Exception:
        pass
    return f"HIBP {r.status_code}"
