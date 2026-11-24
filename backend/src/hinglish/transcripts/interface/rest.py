"""REST v1 for transcripts (ARCHITECTURE §10). Thin: map HTTP <-> use-case commands, nothing else.

Concurrency: responses carry `ETag: "<version>"`; PATCH requires `If-Match` (428 without, 412 on mismatch).
Idempotency: POST accepts `Idempotency-Key`; a retry with the same key and body replays the first response.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Annotated, Any, Literal
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse

from hinglish.platform.idempotency import IdempotencyStore, StoredResponse
from hinglish.shared_kernel.ids import PUBLIC_TENANT
from hinglish.transcripts.api import (
    CreateManualTranscript,
    DeleteTranscript,
    EditSegment,
    RenameTranscript,
    RestoreTranscript,
    SearchQuery,
    TranscriptDetail,
    TranscriptsModule,
)
from hinglish.transcripts.interface.schemas import (
    CreateTranscriptIn,
    EditSegmentIn,
    PageOut,
    RenameIn,
    TranscriptOut,
)
from hinglish.web.problem import MEDIA_TYPE, ApiProblem

router = APIRouter(prefix="/transcripts", tags=["transcripts"])

PROBLEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    code: {"description": desc, "content": {MEDIA_TYPE: {}}}
    for code, desc in {
        404: "Not found",
        409: "Deleted or wrong state",
        412: "Version conflict",
        422: "Invalid input",
        428: "If-Match required",
    }.items()
}


def _module(request: Request) -> TranscriptsModule:
    module: TranscriptsModule = request.app.state.transcripts
    return module


def _etag(version: int) -> str:
    return f'"{version}"'


def _parse_if_match(if_match: str | None, *, required: bool) -> int | None:
    if if_match is None or if_match.strip() == "*":
        if required:
            raise ApiProblem("PRECONDITION_REQUIRED", 'Send If-Match: "<version>" from the last GET.')
        return None
    tag = if_match.strip().removeprefix("W/").strip('"')
    try:
        return int(tag)
    except ValueError as exc:
        raise ApiProblem("PRECONDITION_REQUIRED", "If-Match must be the ETag from the last GET.") from exc


def _detail_response(d: TranscriptDetail, status_code: int = 200, **headers: str) -> JSONResponse:
    body = TranscriptOut.of_detail(d).model_dump(mode="json")
    return JSONResponse(body, status_code=status_code, headers={"ETag": _etag(d.summary.version), **headers})


@router.post("", status_code=201, response_model=TranscriptOut, responses=PROBLEM_RESPONSES)
async def create_transcript(
    body: CreateTranscriptIn,
    request: Request,
    idempotency_key: Annotated[str | None, Header(max_length=200)] = None,
) -> JSONResponse:
    """Create a typed note (engine = manual). Recordings are created by the realtime gateway."""
    store: IdempotencyStore = request.app.state.idempotency
    request_hash = hashlib.sha256(json.dumps(body.model_dump(), sort_keys=True).encode()).hexdigest()
    if idempotency_key:
        stored = await store.get(PUBLIC_TENANT, idempotency_key)
        if stored is not None:
            if stored.request_hash != request_hash:
                raise ApiProblem(
                    "IDEMPOTENCY_KEY_REUSED", "This Idempotency-Key was used with a different body."
                )
            return JSONResponse(
                stored.body,
                status_code=stored.status_code,
                headers={"Idempotent-Replayed": "true", "ETag": _etag(stored.body["version"])},
            )

    detail = await _module(request).create_manual.execute(
        CreateManualTranscript(text=body.text, title=body.title)
    )
    response = _detail_response(detail, 201, Location=f"/api/v1/transcripts/{detail.summary.id}")
    if idempotency_key:
        payload = TranscriptOut.of_detail(detail).model_dump(mode="json")
        await store.put(PUBLIC_TENANT, idempotency_key, StoredResponse(request_hash, 201, payload))
    return response


@router.get("", response_model=PageOut, responses=PROBLEM_RESPONSES)
async def search_transcripts(
    request: Request,
    q: Annotated[str | None, Query(max_length=200, description="Full-text search (title and text).")] = None,
    engine: Literal["sarvam", "manual", "fake"] | None = None,
    created_from: Annotated[datetime | None, Query(alias="from")] = None,
    created_to: Annotated[datetime | None, Query(alias="to")] = None,
    cursor: Annotated[str | None, Query(max_length=500)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PageOut:
    """Newest first, keyset-paginated: pass `next_cursor` back as `cursor`."""
    page = await _module(request).search.execute(
        SearchQuery(
            q=q, engine=engine, created_from=created_from, created_to=created_to, cursor=cursor, limit=limit
        )
    )
    return PageOut.of(page)


@router.get("/{transcript_id}", response_model=TranscriptOut, responses=PROBLEM_RESPONSES)
async def get_transcript(transcript_id: UUID, request: Request) -> JSONResponse:
    return _detail_response(await _module(request).get.execute(transcript_id))


@router.patch("/{transcript_id}", response_model=TranscriptOut, responses=PROBLEM_RESPONSES)
async def rename_transcript(
    transcript_id: UUID,
    body: RenameIn,
    request: Request,
    if_match: Annotated[str | None, Header()] = None,
) -> JSONResponse:
    detail = await _module(request).rename.execute(
        RenameTranscript(transcript_id, body.title, _parse_if_match(if_match, required=True))
    )
    return _detail_response(detail)


@router.patch("/{transcript_id}/segments/{seq}", response_model=TranscriptOut, responses=PROBLEM_RESPONSES)
async def edit_segment(
    transcript_id: UUID,
    seq: int,
    body: EditSegmentIn,
    request: Request,
    if_match: Annotated[str | None, Header()] = None,
) -> JSONResponse:
    detail = await _module(request).edit_segment.execute(
        EditSegment(transcript_id, seq, body.text, _parse_if_match(if_match, required=True))
    )
    return _detail_response(detail)


@router.delete("/{transcript_id}", status_code=204, responses=PROBLEM_RESPONSES)
async def delete_transcript(
    transcript_id: UUID,
    request: Request,
    hard: bool = False,
    if_match: Annotated[str | None, Header()] = None,
) -> Response:
    """Soft delete (restorable) by default; `?hard=true` removes it permanently."""
    await _module(request).delete.execute(
        DeleteTranscript(transcript_id, hard=hard, expected_version=_parse_if_match(if_match, required=False))
    )
    return Response(status_code=204)


@router.post("/{transcript_id}:restore", response_model=TranscriptOut, responses=PROBLEM_RESPONSES)
async def restore_transcript(transcript_id: UUID, request: Request) -> JSONResponse:
    return _detail_response(await _module(request).restore.execute(RestoreTranscript(transcript_id)))


@router.get("/{transcript_id}/export", response_class=PlainTextResponse, responses=PROBLEM_RESPONSES)
async def export_transcript(
    transcript_id: UUID, request: Request, format: Literal["txt"] = "txt"
) -> PlainTextResponse:
    filename, text = await _module(request).export.execute(transcript_id)
    ascii_name = filename if filename.isascii() else "transcript.txt"
    disposition = f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"
    return PlainTextResponse(text, headers={"Content-Disposition": disposition})
