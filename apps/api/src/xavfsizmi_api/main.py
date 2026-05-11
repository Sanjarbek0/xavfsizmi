"""FastAPI app factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .core.errors import install_problem_handlers
from .routers import (
    admin,
    api_keys,
    auth,
    billing,
    breaches,
    domains,
    health,
    notifications,
    passwords,
    public_api,
)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # placeholder for db / redis warm-up; wired in later phases
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=f"{settings.brand_name} API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    install_problem_handlers(app)

    app.include_router(health.router)
    app.include_router(breaches.router, prefix="/v1")
    app.include_router(passwords.router, prefix="/v1")
    app.include_router(notifications.router, prefix="/v1")
    app.include_router(auth.router, prefix="/v1")
    app.include_router(api_keys.router, prefix="/v1")
    app.include_router(domains.router, prefix="/v1")
    app.include_router(public_api.router, prefix="/v1")
    app.include_router(admin.router, prefix="/v1")
    app.include_router(billing.router, prefix="/v1")
    app.include_router(billing.webhook_router, prefix="/v1")
    return app


app = create_app()
