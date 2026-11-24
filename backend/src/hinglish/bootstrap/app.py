"""FastAPI application factory. Mounts routers according to APP_ROLES."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from hinglish.bootstrap.container import build_container
from hinglish.bootstrap.settings import Settings, get_settings
from hinglish.observability.health import router as health_router
from hinglish.observability.logging import configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.container = build_container(settings)
        yield

    app = FastAPI(
        title="Hinglish Live Transcribe API",
        version="0.1.0",
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/docs",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["ETag"],
    )
    app.include_router(health_router, prefix="/api/v1")
    # Role-gated routers are added here as contexts are built:
    #   "api"     -> transcripts, speech REST
    #   "gateway" -> /ws/v1/transcribe
    return app
