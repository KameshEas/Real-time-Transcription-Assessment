"""Transcript aggregate (root) and its Segment entities. ARCHITECTURE §7.

Invariants
- segment `seq` is strictly increasing and unique within a transcript
- a deleted transcript rejects every change except restore
- segments are appended only while recording
- editing a segment marks the transcript `edited`, re-derives tags and Hindi ratio, and drops cached
  script conversions of that segment (they no longer match its text)
- every state change bumps `version` (optimistic concurrency, `If-Match`)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from hinglish.shared_kernel import Entity, TenantId
from hinglish.shared_kernel.language import TaggedWords, hindi_ratio
from hinglish.transcripts.domain.errors import (
    InvalidStateTransition,
    InvalidValue,
    SegmentNotFound,
    TranscriptIsDeleted,
)
from hinglish.transcripts.domain.events import (
    SegmentFinalized,
    TranscriptCompleted,
    TranscriptCreated,
    TranscriptDeleted,
    TranscriptEdited,
    TranscriptRestored,
)
from hinglish.transcripts.domain.value_objects import (
    Engine,
    ScriptMode,
    SegmentText,
    Title,
    TranscriptStatus,
)

DEFAULT_TITLE = "Untitled"
AUTO_TITLE_CHARS = 60


@dataclass
class Segment:
    seq: int
    text: str
    words: TaggedWords
    start_ms: int | None = None
    end_ms: int | None = None
    language: str | None = None
    text_deva: str | None = None
    text_roman: str | None = None


@dataclass
class TranscriptState:
    """Plain persisted fields, used by repositories to rebuild the aggregate."""

    id: UUID
    tenant_id: TenantId
    title: str
    engine: Engine
    script_mode: ScriptMode
    status: TranscriptStatus
    created_at: datetime
    updated_at: datetime
    owner_id: str | None = None
    model_id: str | None = None
    edited: bool = False
    duration_ms: int | None = None
    version: int = 1
    deleted_at: datetime | None = None
    segments: list[Segment] = field(default_factory=list)


class Transcript(Entity):
    def __init__(self, state: TranscriptState) -> None:
        super().__init__(state.id)
        self._s = state
        self._segments = sorted(state.segments, key=lambda seg: seg.seq)
        self._dirty_seqs: set[int] = set()

    # --- factories ------------------------------------------------------------------------------

    @classmethod
    def start_recording(
        cls,
        *,
        id: UUID,
        tenant_id: TenantId,
        engine: Engine,
        script_mode: ScriptMode,
        now: datetime,
        model_id: str | None = None,
        owner_id: str | None = None,
    ) -> Transcript:
        t = cls(
            TranscriptState(
                id=id,
                tenant_id=tenant_id,
                title=DEFAULT_TITLE,
                engine=engine,
                script_mode=script_mode,
                status=TranscriptStatus.RECORDING,
                created_at=now,
                updated_at=now,
                model_id=model_id,
                owner_id=owner_id,
            )
        )
        t.record(TranscriptCreated(aggregate_id=id, engine=engine.value))
        return t

    @classmethod
    def create_manual(
        cls,
        *,
        id: UUID,
        tenant_id: TenantId,
        title: Title | None,
        segments: list[tuple[SegmentText, TaggedWords]],
        now: datetime,
        owner_id: str | None = None,
    ) -> Transcript:
        if not segments:
            raise InvalidValue("Text can't be empty.", field="text")
        t = cls(
            TranscriptState(
                id=id,
                tenant_id=tenant_id,
                title=str(title) if title else DEFAULT_TITLE,
                engine=Engine.MANUAL,
                script_mode=ScriptMode.MIXED,
                status=TranscriptStatus.COMPLETED,
                created_at=now,
                updated_at=now,
                owner_id=owner_id,
            )
        )
        for text, words in segments:
            t._add_segment(text, words)
        if title is None:
            t._auto_title()
        t.record(TranscriptCreated(aggregate_id=id, engine=Engine.MANUAL.value))
        return t

    # --- live recording -------------------------------------------------------------------------

    def append_segment(
        self,
        text: SegmentText,
        words: TaggedWords,
        *,
        now: datetime,
        start_ms: int | None = None,
        end_ms: int | None = None,
        language: str | None = None,
    ) -> Segment:
        self._ensure_not_deleted()
        if self._s.status is not TranscriptStatus.RECORDING:
            raise InvalidStateTransition("Segments can only be added while recording.")
        seg = self._add_segment(text, words, start_ms=start_ms, end_ms=end_ms, language=language)
        if len(self._segments) == 1 and self._s.title == DEFAULT_TITLE:
            self._auto_title()
        self._touch(now)
        self.record(SegmentFinalized(aggregate_id=self.id, seq=seg.seq))
        return seg

    def complete(self, *, now: datetime, duration_ms: int | None) -> None:
        self._ensure_not_deleted()
        if self._s.status is TranscriptStatus.COMPLETED:
            return  # idempotent: stop can race with a disconnect
        self._s.status = TranscriptStatus.COMPLETED
        if duration_ms is not None:
            self._s.duration_ms = (self._s.duration_ms or 0) + duration_ms
        self._touch(now)
        self.record(TranscriptCompleted(aggregate_id=self.id, duration_ms=self._s.duration_ms))

    def reopen_for_recording(self, *, now: datetime) -> None:
        """Resume after a dropped connection (FR-1.6): numbering continues from the last segment."""
        self._ensure_not_deleted()
        if self._s.engine is Engine.MANUAL:
            raise InvalidStateTransition("A typed note can't be resumed as a recording.")
        if self._s.status is TranscriptStatus.RECORDING:
            return
        self._s.status = TranscriptStatus.RECORDING
        self._touch(now)

    # --- editing --------------------------------------------------------------------------------

    def rename(self, title: Title, *, now: datetime) -> None:
        self._ensure_not_deleted()
        if title.value == self._s.title:
            return
        self._s.title = title.value
        self._touch(now)
        self.record(TranscriptEdited(aggregate_id=self.id, what="title"))

    def edit_segment(self, seq: int, text: SegmentText, words: TaggedWords, *, now: datetime) -> Segment:
        self._ensure_not_deleted()
        seg = self.segment(seq)
        if text.value == seg.text:
            return seg
        seg.text = text.value
        seg.words = words
        seg.text_deva = None
        seg.text_roman = None
        self._s.edited = True
        self._dirty_seqs.add(seq)
        self._touch(now)
        self.record(TranscriptEdited(aggregate_id=self.id, what="segment", seq=seq))
        return seg

    # --- deletion -------------------------------------------------------------------------------

    def soft_delete(self, *, now: datetime) -> None:
        if self._s.deleted_at is not None:
            return
        self._s.deleted_at = now
        self._touch(now)
        self.record(TranscriptDeleted(aggregate_id=self.id, hard=False))

    def restore(self, *, now: datetime) -> None:
        if self._s.deleted_at is None:
            return
        self._s.deleted_at = None
        self._touch(now)
        self.record(TranscriptRestored(aggregate_id=self.id))

    def mark_hard_deleted(self) -> None:
        self.record(TranscriptDeleted(aggregate_id=self.id, hard=True))

    # --- reads ----------------------------------------------------------------------------------

    @property
    def state(self) -> TranscriptState:
        self._s.segments = self._segments
        return self._s

    @property
    def segments(self) -> tuple[Segment, ...]:
        return tuple(self._segments)

    def segment(self, seq: int) -> Segment:
        for seg in self._segments:
            if seg.seq == seq:
                return seg
        raise SegmentNotFound(f"Segment {seq} not found.")

    @property
    def last_seq(self) -> int:
        return self._segments[-1].seq if self._segments else 0

    @property
    def full_text(self) -> str:
        return "\n".join(seg.text for seg in self._segments)

    @property
    def hindi_ratio(self) -> float | None:
        return hindi_ratio([seg.words for seg in self._segments])

    @property
    def version(self) -> int:
        return self._s.version

    @property
    def is_deleted(self) -> bool:
        return self._s.deleted_at is not None

    def pull_dirty_segments(self) -> list[Segment]:
        """Segments added or changed since load; the repository writes only these."""
        dirty = [seg for seg in self._segments if seg.seq in self._dirty_seqs]
        self._dirty_seqs.clear()
        return dirty

    # --- internals ------------------------------------------------------------------------------

    def _add_segment(
        self,
        text: SegmentText,
        words: TaggedWords,
        *,
        start_ms: int | None = None,
        end_ms: int | None = None,
        language: str | None = None,
    ) -> Segment:
        seg = Segment(
            seq=self.last_seq + 1,
            text=text.value,
            words=words,
            start_ms=start_ms,
            end_ms=end_ms,
            language=language,
        )
        self._segments.append(seg)
        self._dirty_seqs.add(seg.seq)
        return seg

    def _auto_title(self) -> None:
        first = self._segments[0].text
        if len(first) <= AUTO_TITLE_CHARS:
            self._s.title = first
        else:
            cut = first[:AUTO_TITLE_CHARS].rsplit(" ", 1)[0]
            self._s.title = f"{cut}…"

    def _touch(self, now: datetime) -> None:
        self._s.updated_at = now
        self._s.version += 1

    def _ensure_not_deleted(self) -> None:
        if self._s.deleted_at is not None:
            raise TranscriptIsDeleted("This transcript was deleted. Restore it first.")
