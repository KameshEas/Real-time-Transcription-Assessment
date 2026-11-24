"""Read-side shapes returned by use cases and queries (no domain objects leak to interfaces)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from hinglish.shared_kernel.language import TaggedWords
from hinglish.transcripts.domain.transcript import Segment, Transcript

PREVIEW_CHARS = 200


@dataclass(frozen=True, slots=True)
class SegmentView:
    seq: int
    text: str
    words: TaggedWords
    start_ms: int | None
    end_ms: int | None
    language: str | None
    text_deva: str | None
    text_roman: str | None

    @classmethod
    def of(cls, seg: Segment) -> SegmentView:
        return cls(
            seq=seg.seq,
            text=seg.text,
            words=seg.words,
            start_ms=seg.start_ms,
            end_ms=seg.end_ms,
            language=seg.language,
            text_deva=seg.text_deva,
            text_roman=seg.text_roman,
        )


@dataclass(frozen=True, slots=True)
class TranscriptSummary:
    id: UUID
    title: str
    engine: str
    script_mode: str
    status: str
    hindi_ratio: float | None
    edited: bool
    duration_ms: int | None
    segment_count: int
    preview: str
    version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class TranscriptDetail:
    summary: TranscriptSummary
    segments: tuple[SegmentView, ...]

    @classmethod
    def of(cls, t: Transcript) -> TranscriptDetail:
        s = t.state
        full = t.full_text
        return cls(
            summary=TranscriptSummary(
                id=s.id,
                title=s.title,
                engine=s.engine.value,
                script_mode=s.script_mode.value,
                status=s.status.value,
                hindi_ratio=t.hindi_ratio,
                edited=s.edited,
                duration_ms=s.duration_ms,
                segment_count=len(t.segments),
                preview=full[:PREVIEW_CHARS],
                version=s.version,
                created_at=s.created_at,
                updated_at=s.updated_at,
            ),
            segments=tuple(SegmentView.of(seg) for seg in t.segments),
        )


@dataclass(frozen=True, slots=True)
class SearchQuery:
    q: str | None = None
    engine: str | None = None
    created_from: datetime | None = None
    created_to: datetime | None = None
    cursor: str | None = None
    limit: int = 20


@dataclass(frozen=True, slots=True)
class Page:
    items: tuple[TranscriptSummary, ...] = field(default_factory=tuple)
    next_cursor: str | None = None


@dataclass(frozen=True, slots=True)
class RecordingHandle:
    transcript_id: UUID
    last_seq: int
