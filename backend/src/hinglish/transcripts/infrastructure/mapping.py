"""Rows <-> aggregate mapping, shared by the repository (write side) and read model."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from hinglish.shared_kernel import TenantId
from hinglish.shared_kernel.language import TaggedWords
from hinglish.transcripts.domain.transcript import Segment, Transcript, TranscriptState
from hinglish.transcripts.domain.value_objects import Engine, ScriptMode, TranscriptStatus


def to_aggregate(row: Mapping[Any, Any], segment_rows: Sequence[Mapping[Any, Any]]) -> Transcript:
    return Transcript(
        TranscriptState(
            id=row["id"],
            tenant_id=TenantId(row["tenant_id"]),
            owner_id=row["owner_id"],
            title=row["title"],
            engine=Engine(row["engine"]),
            model_id=row["model_id"],
            script_mode=ScriptMode(row["script_mode"]),
            status=TranscriptStatus(row["status"]),
            edited=row["edited"],
            duration_ms=row["duration_ms"],
            version=row["version"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            deleted_at=row["deleted_at"],
            segments=[to_segment(r) for r in segment_rows],
        )
    )


def to_segment(r: Mapping[Any, Any]) -> Segment:
    return Segment(
        seq=r["seq"],
        text=r["text"],
        words=TaggedWords.from_dict(r["words"]),
        start_ms=r["start_ms"],
        end_ms=r["end_ms"],
        language=r["language"],
        text_deva=r["text_deva"],
        text_roman=r["text_roman"],
    )


def transcript_row(t: Transcript) -> dict[str, Any]:
    s = t.state
    return {
        "id": s.id,
        "tenant_id": s.tenant_id,
        "owner_id": s.owner_id,
        "title": s.title,
        "engine": s.engine.value,
        "model_id": s.model_id,
        "script_mode": s.script_mode.value,
        "full_text": t.full_text,
        "hindi_ratio": t.hindi_ratio,
        "edited": s.edited,
        "duration_ms": s.duration_ms,
        "segment_count": len(t.segments),
        "status": s.status.value,
        "version": s.version,
        "created_at": s.created_at,
        "updated_at": s.updated_at,
        "deleted_at": s.deleted_at,
    }


def segment_row(transcript_id: Any, seg: Segment) -> dict[str, Any]:
    return {
        "transcript_id": transcript_id,
        "seq": seg.seq,
        "start_ms": seg.start_ms,
        "end_ms": seg.end_ms,
        "text": seg.text,
        "text_deva": seg.text_deva,
        "text_roman": seg.text_roman,
        "language": seg.language,
        "words": seg.words.to_dict(),
    }
