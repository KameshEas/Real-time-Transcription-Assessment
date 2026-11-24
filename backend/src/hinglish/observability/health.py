from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

log = structlog.get_logger()
router = APIRouter(prefix="/health", tags=["health"])
DB_PING_TIMEOUT_S = 3.0


@router.get("/live")
async def live() -> dict[str, str]:
    """The process is up (no dependencies checked)."""
    return {"status": "ok"}


@router.get("/ready")
async def ready(request: Request) -> JSONResponse:
    """Ready to serve: database reachable (when used) and which engines/vendors are configured.
    503 when the database is down, so load balancers stop routing here."""
    s = request.app.state.settings
    ping: Callable[[], Awaitable[None]] | None = getattr(request.app.state, "db_ping", None)
    database = "memory"
    if ping is not None:
        try:
            async with asyncio.timeout(DB_PING_TIMEOUT_S):
                await ping()
            database = "ok"
        except Exception as exc:
            log.warning("health.db_down", error=type(exc).__name__)
            database = "down"
    body = {
        "status": "ok" if database != "down" else "degraded",
        "roles": s.app_roles,
        "database": database,
        "engines": sorted(getattr(request.app.state, "recognizers", {})),
        "vendors": {
            "sarvam": s.sarvam_api_key is not None,
            "groq": s.groq_api_key is not None,
        },
    }
    return JSONResponse(body, status_code=503 if database == "down" else 200)
