from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready(request: Request) -> dict[str, object]:
    s = request.app.state.settings
    return {
        "status": "ok",
        "roles": s.app_roles,
        "vendors": {
            "sarvam": s.sarvam_api_key is not None,
            "groq": s.groq_api_key is not None,
        },
        # TODO(Day 2): add DB ping and circuit-breaker states.
    }
