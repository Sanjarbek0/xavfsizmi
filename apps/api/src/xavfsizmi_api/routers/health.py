"""Health, readiness, and version endpoints."""

from __future__ import annotations

import inspect
from typing import Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel
from sqlalchemy import text

from .. import __version__
from ..config import get_settings
from ..deps import RedisDep, SessionDep

router = APIRouter(tags=["health"])


class ReadinessReport(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok", "fail"]
    redis: Literal["ok", "fail"]


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness probe — process is up. No dependency calls."""

    return {"status": "ok"}


@router.get("/version")
async def version() -> dict[str, str]:
    return {"version": __version__, "brand": get_settings().brand_name}


@router.get("/readyz", response_model=ReadinessReport)
async def readyz(
    response: Response,
    session: SessionDep,
    redis: RedisDep,
) -> ReadinessReport:
    """Readiness probe — checks DB and Redis connectivity."""

    db_status: Literal["ok", "fail"] = "ok"
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        db_status = "fail"

    redis_status: Literal["ok", "fail"] = "ok"
    try:
        result = redis.ping()
        pong = await result if inspect.isawaitable(result) else result
        if not pong:
            redis_status = "fail"
    except Exception:
        redis_status = "fail"

    overall: Literal["ok", "degraded"] = (
        "ok" if db_status == "ok" and redis_status == "ok" else "degraded"
    )
    if overall != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessReport(status=overall, database=db_status, redis=redis_status)
