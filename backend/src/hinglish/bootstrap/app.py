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
from hinglish.transcription.interface.ws_gateway import router as gateway_router
from hinglish.transcripts.interface.rest import router as transcripts_router
from hinglish.web.problem import install_problem_handlers


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        container = build_container(settings)
        app.state.container = container
        # Interface adapters read only what they need, never the container type itself.
        app.state.recognizers = container.recognizers
        app.state.session_policy = container.session_policy
        app.state.live_transcription = container.live_transcription
        app.state.transcripts = container.transcripts
        app.state.idempotency = container.idempotency
        app.state.db_ping = container.db_ping
        try:
            yield
        finally:
            await container.aclose()

    app = FastAPI(
        title="Hinglish Live Transcribe API",
        version="0.2.0",
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
        expose_headers=["ETag", "Location", "Idempotent-Replayed", "Content-Disposition"],
    )
    install_problem_handlers(app)
    app.include_router(health_router, prefix="/api/v1")
    if "api" in settings.app_roles:
        app.include_router(transcripts_router, prefix="/api/v1")
    if "gateway" in settings.app_roles:
        app.include_router(gateway_router)
    return app
