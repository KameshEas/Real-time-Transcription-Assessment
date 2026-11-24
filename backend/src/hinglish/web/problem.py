"""RFC 9457 Problem Details for every error response. Internals never leak: unexpected errors are logged
with a request id and returned as a generic 500."""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from hinglish.shared_kernel import DomainError

log = structlog.get_logger()
MEDIA_TYPE = "application/problem+json"

# Stable error code -> (HTTP status, title)
STATUS: dict[str, tuple[int, str]] = {
    "INVALID_VALUE": (422, "Invalid value"),
    "VALIDATION_ERROR": (422, "Invalid request"),
    "TRANSCRIPT_NOT_FOUND": (404, "Transcript not found"),
    "SEGMENT_NOT_FOUND": (404, "Segment not found"),
    "TRANSCRIPT_DELETED": (409, "Transcript is deleted"),
    "INVALID_STATE": (409, "Not allowed in the current state"),
    "VERSION_CONFLICT": (412, "Version conflict"),
    "PRECONDITION_REQUIRED": (428, "If-Match header required"),
    "IDEMPOTENCY_KEY_REUSED": (422, "Idempotency key reused"),
    "NOT_FOUND": (404, "Not found"),
    "METHOD_NOT_ALLOWED": (405, "Method not allowed"),
    "INTERNAL": (500, "Internal error"),
}


class ApiProblem(Exception):
    """Raised by interface code for HTTP-level problems (missing headers, reused keys)."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def problem(request: Request, code: str, detail: str | None = None, **extra: Any) -> JSONResponse:
    status, title = STATUS.get(code, (400, "Bad request"))
    body: dict[str, Any] = {
        "type": f"/problems/{code.lower().replace('_', '-')}",
        "title": title,
        "status": status,
        "detail": detail or title,
        "instance": request.url.path,
        "code": code,
        **extra,
    }
    return JSONResponse(body, status_code=status, media_type=MEDIA_TYPE)


def install_problem_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain(request: Request, exc: DomainError) -> JSONResponse:
        extra: dict[str, Any] = {}
        if (field := getattr(exc, "field", None)) is not None:
            extra["errors"] = [{"field": field, "message": str(exc)}]
        return problem(request, exc.code, str(exc), **extra)

    @app.exception_handler(ApiProblem)
    async def _api(request: Request, exc: ApiProblem) -> JSONResponse:
        return problem(request, exc.code, exc.detail)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {
                "field": ".".join(str(p) for p in e["loc"] if p not in ("body", "query", "path")),
                "message": e["msg"],
            }
            for e in exc.errors()
        ]
        return problem(request, "VALIDATION_ERROR", "Some fields are invalid.", errors=errors)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(exc.status_code, "INTERNAL")
        return problem(request, code, str(exc.detail))

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
        log.exception("http.unhandled", path=request.url.path)
        return problem(request, "INTERNAL", "Something went wrong on our side.")
