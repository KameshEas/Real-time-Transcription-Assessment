"""HTTP request/response models (OpenAPI 3.1 source for the generated TypeScript client)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from hinglish.transcripts.api import Page, SegmentView, TranscriptDetail, TranscriptSummary


class CreateTranscriptIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=100_000, description="Pasted text; one segment per line.")
    title: str | None = Field(default=None, max_length=200)


class RenameIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)


class EditSegmentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=5_000)


class WordOut(BaseModel):
    w: str
    lang: Literal["hi", "en", "other"]


class SegmentOut(BaseModel):
    seq: int
    text: str
    words: list[WordOut]
    start_ms: int | None
    end_ms: int | None
    language: str | None
    text_deva: str | None
    text_roman: str | None

    @classmethod
    def of(cls, s: SegmentView) -> SegmentOut:
        return cls(
            seq=s.seq,
            text=s.text,
            words=[WordOut(w=t.w, lang=t.lang) for t in s.words.items],
            start_ms=s.start_ms,
            end_ms=s.end_ms,
            language=s.language,
            text_deva=s.text_deva,
            text_roman=s.text_roman,
        )


class TranscriptSummaryOut(BaseModel):
    id: UUID
    title: str
    engine: Literal["sarvam", "manual", "fake"]
    script_mode: Literal["mixed", "devanagari", "roman"]
    status: Literal["recording", "completed"]
    hindi_ratio: float | None = Field(description="Share of Hindi among Hindi+English words, 0 to 1.")
    edited: bool
    duration_ms: int | None
    segment_count: int
    preview: str
    version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, s: TranscriptSummary) -> TranscriptSummaryOut:
        return cls.model_validate(s, from_attributes=True)


class TranscriptOut(TranscriptSummaryOut):
    segments: list[SegmentOut]

    @classmethod
    def of_detail(cls, d: TranscriptDetail) -> TranscriptOut:
        base = TranscriptSummaryOut.of(d.summary).model_dump()
        return cls(**base, segments=[SegmentOut.of(s) for s in d.segments])


class PageOut(BaseModel):
    items: list[TranscriptSummaryOut]
    next_cursor: str | None

    @classmethod
    def of(cls, p: Page) -> PageOut:
        return cls(items=[TranscriptSummaryOut.of(s) for s in p.items], next_cursor=p.next_cursor)
