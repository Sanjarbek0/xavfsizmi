"""Cloudflare Turnstile token verification.

If `TURNSTILE_SECRET_KEY` is empty (e.g. local dev) the verifier short-circuits
to ``True`` so test environments work without contacting Cloudflare.
"""

from __future__ import annotations

import httpx

from ..config import Settings, get_settings

VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


class TurnstileVerifier:
    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._client = client

    async def verify(self, token: str | None, *, remote_ip: str | None = None) -> bool:
        secret = self._settings.turnstile_secret_key
        if not secret:
            return True
        if not token:
            return False
        client = self._client or httpx.AsyncClient(timeout=5.0)
        owns_client = self._client is None
        data = {"secret": secret, "response": token}
        if remote_ip:
            data["remoteip"] = remote_ip
        try:
            r = await client.post(VERIFY_URL, data=data)
        except httpx.HTTPError:
            return False
        finally:
            if owns_client:
                await client.aclose()
        if r.status_code != 200:
            return False
        try:
            payload = r.json()
        except ValueError:
            return False
        return bool(payload.get("success"))
