"""Structured logging, Sentry, and Prometheus metrics wiring.

The :func:`configure_logging` call replaces the root logging handlers with a
``structlog`` setup so every log line (including stdlib ``logging`` calls from
SQLAlchemy / uvicorn / etc.) gets the same JSON shape with request context
injected.

:func:`init_sentry` is a no-op when ``SENTRY_DSN`` is empty; otherwise it
initialises the SDK with FastAPI/Starlette integrations.

:class:`HTTP_REQUESTS` / :class:`HTTP_LATENCY` are module-level Prometheus
collectors. The :func:`RequestObservabilityMiddleware` middleware below records
every HTTP request into them and binds a ``request_id`` to the structlog
context so downstream log lines automatically include it.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from prometheus_client import Counter, Histogram
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

HTTP_REQUESTS: Counter = Counter(
    "xavfsizmi_http_requests_total",
    "Total HTTP requests handled by the API, labelled with method, route, and status family.",
    labelnames=("method", "route", "status"),
)
HTTP_LATENCY: Histogram = Histogram(
    "xavfsizmi_http_request_duration_seconds",
    "Wall-clock latency of HTTP requests, by route.",
    labelnames=("method", "route"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)


def _route_label(request: Request) -> str:
    """Return a low-cardinality route label (template path, not the live URL).

    We deliberately avoid the raw ``request.url.path`` because it would create
    one Prometheus series per ``/v1/account/api-keys/{id}/usage`` instance and
    blow up the metric cardinality.
    """
    route = request.scope.get("route")
    if route is not None and hasattr(route, "path_format"):
        return str(route.path_format)
    if route is not None and hasattr(route, "path"):
        return str(route.path)
    return request.url.path


def _status_family(status_code: int) -> str:
    return f"{status_code // 100}xx"


def configure_logging(*, level: str = "INFO", json_logs: bool = True) -> None:
    """Wire ``structlog`` into the stdlib ``logging`` root.

    Idempotent — safe to call multiple times (handlers are cleared first), which
    is important because pytest re-imports the app between test modules.
    """
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        timestamper,
        structlog.processors.StackInfoRenderer(),
    ]
    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.format_exc_info,
            (
                structlog.processors.JSONRenderer()
                if json_logs
                else structlog.dev.ConsoleRenderer(colors=False)
            ),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping().get(level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    # Hook stdlib logging through structlog so uvicorn / sqlalchemy lines also
    # come out as JSON.
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    handler = logging.StreamHandler()
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processor=(
                structlog.processors.JSONRenderer()
                if json_logs
                else structlog.dev.ConsoleRenderer(colors=False)
            ),
            foreign_pre_chain=shared_processors,
        )
    )
    root.addHandler(handler)
    root.setLevel(level.upper())


def init_sentry(*, dsn: str, env: str, traces_sample_rate: float) -> None:
    """Initialise Sentry if a DSN is configured. No-op otherwise.

    Imported lazily so test runs without ``SENTRY_DSN`` don't pay the import
    cost or open a network client.
    """
    if not dsn:
        return
    import sentry_sdk
    from sentry_sdk.integrations.asyncio import AsyncioIntegration
    from sentry_sdk.integrations.starlette import StarletteIntegration

    sentry_sdk.init(
        dsn=dsn,
        environment=env,
        traces_sample_rate=traces_sample_rate,
        send_default_pii=False,
        integrations=[StarletteIntegration(), AsyncioIntegration()],
    )


class RequestObservabilityMiddleware(BaseHTTPMiddleware):
    """Per-request logging + metrics + correlation id.

    - Generates a ``X-Request-ID`` (or honours the inbound one) and echoes it
      back on the response so a single request can be traced across services.
    - Times every request and records it in ``HTTP_REQUESTS`` / ``HTTP_LATENCY``.
    - Binds ``request_id``, ``method``, ``path``, ``status`` to the structlog
      context so any log line emitted inside the handler picks them up.
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )
        log = structlog.get_logger("http")
        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers.setdefault("x-request-id", request_id)
            return response
        except Exception:
            log.exception("request_failed")
            raise
        finally:
            elapsed = time.perf_counter() - start
            route = _route_label(request)
            HTTP_REQUESTS.labels(
                method=request.method, route=route, status=_status_family(status_code)
            ).inc()
            HTTP_LATENCY.labels(method=request.method, route=route).observe(elapsed)
            structlog.contextvars.bind_contextvars(
                status=status_code, duration_ms=round(elapsed * 1000, 2)
            )
            log.info("request_completed")
