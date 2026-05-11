"""Prometheus ``/metrics`` endpoint.

Kept on the bare app root (not under ``/v1``) so a scraper can hit it without
caring about API versioning. Optionally protected by a static bearer token —
the operator sets ``METRICS_TOKEN`` and configures Prometheus's ``bearer_token``
to match.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from ..core.errors import ProblemError
from ..deps import SettingsDep

router = APIRouter(tags=["meta"])


@router.get("/metrics", include_in_schema=False)
async def metrics(request: Request, settings: SettingsDep) -> Response:
    if not settings.metrics_enabled:
        raise ProblemError(status=404)
    if settings.metrics_token:
        auth = request.headers.get("authorization") or ""
        if (
            not auth.startswith("Bearer ")
            or auth.removeprefix("Bearer ").strip() != settings.metrics_token
        ):
            raise ProblemError(status=401, detail_key="auth.session_invalid")
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
