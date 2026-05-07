"""Pwned Passwords k-anonymity proxy.

In production, password lookups go directly to the Cloudflare Worker that
serves the k-anonymity range files from R2. This router is a thin
fallback that forwards to HIBP's free Pwned Passwords API for development
and integration tests.
"""

from __future__ import annotations

import re

import httpx
from fastapi import APIRouter, HTTPException, Path, status
from fastapi.responses import PlainTextResponse

from ..config import get_settings

router = APIRouter(prefix="/passwords", tags=["passwords"])

PREFIX_RE = re.compile(r"^[0-9A-F]{5}$", re.IGNORECASE)


@router.get("/range/{prefix}", response_class=PlainTextResponse)
async def range_lookup(
    prefix: str = Path(min_length=5, max_length=5),
    mode: str = "sha1",
) -> PlainTextResponse:
    if not PREFIX_RE.match(prefix):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bad prefix")
    settings = get_settings()
    base = "https://api.pwnedpasswords.com/range"
    url = f"{base}/{prefix.upper()}"
    params = {"mode": "ntlm"} if mode == "ntlm" else {}
    headers = {"User-Agent": settings.hibp_user_agent}
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(url, params=params, headers=headers)
        if r.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, detail=f"upstream {r.status_code}"
            )
        return PlainTextResponse(content=r.text)
