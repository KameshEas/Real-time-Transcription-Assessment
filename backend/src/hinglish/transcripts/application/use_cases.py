"""Transcripts use cases (one class each, `execute(command)`). ARCHITECTURE §8.

Commands load the aggregate through a unit of work, call domain methods and commit; queries go to the
read model. `expected_version` implements `If-Match` (optimistic concurrency).
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from hinglish.shared_kernel import Clock, TenantId, new_id
from hinglish.shared_kernel.ids import PUBLIC_TENANT
from hinglish.transcripts.application.dto import (
    Page,
    RecordingHandle,
    SearchQuery,
    SegmentView,
    TranscriptDetail,
)
from hinglish.transcripts.application.ports import (
    Tagger,
    TranscriptReadModel,
    UnitOfWork,
    UnitOfWorkFactory,
)
from hinglish.transcripts.domain.errors import InvalidValue, TranscriptNotFound, VersionConflict
from hinglish.transcripts.domain.transcript import Transcript
from hinglish.transcripts.domain.value_objects import (
    MANUAL_TEXT_MAX,
    SEGMENT_MAX,
    Engine,
    ScriptMode,
    SegmentText,
    Title,
)

APPEND_RETRIES = 3  # an append can race a user edit of the same transcript


@dataclass(frozen=True)
class Deps:
    uow: UnitOfWorkFactory
    clock: Clock
    tag: Tagger


async def _load(
    uow: UnitOfWork, tenant_id: TenantId, id: UUID, *, include_deleted: bool = False
) -> Transcript:
    t = await uow.transcripts.get(tenant_id, id, include_deleted=include_deleted)
    if t is None:
        raise TranscriptNotFound("Transcript not found.")
    return t


def _check_version(t: Transcript, expected: int | None) -> None:
    if expected is not None and expected != t.version:
        raise VersionConflict(
            f"This transcript changed since you loaded it (version {t.version}, you had {expected}). "
            "Reload and try again."
        )


# --- live recording (called by the Transcription context through transcripts.api) -----------------


@dataclass(frozen=True)
class StartRecording:
    engine: str
    script: str
    model_id: str | None = None
    tenant_id: TenantId = PUBLIC_TENANT


class StartRecordingHandler:
    def __init__(self, deps: Deps) -> None:
        self.d = deps

    async def execute(self, cmd: StartRecording) -> RecordingHandle:
        t = Transcript.start_recording(
            id=new_id(),
            tenant_id=cmd.tenant_id,
            engine=Engine(cmd.engine),
            script_mode=ScriptMode(cmd.script),
            model_id=cmd.model_id,
            now=self.d.clock.now(),
        )
        async with self.d.uow() as uow:
            uow.transcripts.add(t)
            await uow.commit()
        return RecordingHandle(transcript_id=t.id, last_seq=0)


@dataclass(frozen=True)
class ResumeRecording:
    transcript_id: UUID
    tenant_id: TenantId = PUBLIC_TENANT


class ResumeRecordingHandler:
    def __init__(self, deps: Deps) -> None:
        self.d = deps

    async def execute(self, cmd: ResumeRecording) -> RecordingHandle:
        async with self.d.uow() as uow:
            t = await _load(uow, cmd.tenant_id, cmd.transcript_id)
            t.reopen_for_recording(now=self.d.clock.now())
            await uow.commit()
        return RecordingHandle(transcript_id=t.id, last_seq=t.last_seq)


@dataclass(frozen=True)
class AppendFinal:
    transcript_id: UUID
    text: str
    language: str | None = None
    start_ms: int | None = None
    end_ms: int | None = None
    tenant_id: TenantId = PUBLIC_TENANT


class AppendFinalHandler:
    def __init__(self, deps: Deps) -> None:
        self.d = deps

    async def execute(self, cmd: AppendFinal) -> SegmentView:
        text = SegmentText(cmd.text[:SEGMENT_MAX])
        words = self.d.tag(text.value)
        for attempt in range(APPEND_RETRIES):
            try:
                async with self.d.uow() as uow:
                    t = await _load(uow, cmd.tenant_id, cmd.transcript_id)
                    seg = t.append_segment(
                        text,
                        words,
                        now=self.d.clock.now(),
                        start_ms=cmd.start_ms,
                        end_ms=cmd.end_ms,
                        language=cmd.language,
                    )
                    await uow.commit()
                    return SegmentView.of(seg)
            except VersionConflict:
                if attempt == APPEND_RETRIES - 1:
                    raise
        raise AssertionError("unreachable")


@dataclass(frozen=True)
class CompleteRecording:
    transcript_id: UUID
    duration_ms: int | None
    tenant_id: TenantId = PUBLIC_TENANT


class CompleteRecordingHandler:
    def __init__(self, deps: Deps) -> None:
        self.d = deps

    async def execute(self, cmd: CompleteRecording) -> None:
        for attempt in range(APPEND_RETRIES):
            try:
                async with self.d.uow() as uow:
                    t = await uow.transcripts.get(cmd.tenant_id, cmd.transcript_id)
                    if t is None:
                        return  # deleted while recording: nothing to complete
                    t.complete(now=self.d.clock.now(), duration_ms=cmd.duration_ms)
                    await uow.commit()
                    return
            except VersionConflict:
                if attempt == APPEND_RETRIES - 1:
                    raise


# --- dashboard commands ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CreateManualTranscript:
    text: str
    title: str | None = None
    tenant_id: TenantId = PUBLIC_TENANT


class CreateManualTranscriptHandler:
    def __init__(self, deps: Deps) -> None:
        self.d = deps

    async def execute(self, cmd: CreateManualTranscript) -> TranscriptDetail:
        if len(cmd.text) > MANUAL_TEXT_MAX:
            raise InvalidValue(f"Text must be at most {MANUAL_TEXT_MAX:,} characters.", field="text")
        segments = [(SegmentText(chunk), self.d.tag(chunk)) for chunk in split_into_segments(cmd.text)]
        t = Transcript.create_manual(
            id=new_id(),
            tenant_id=cmd.tenant_id,
            title=Title(cmd.title) if cmd.title and cmd.title.strip() else None,
            segments=segments,
            now=self.d.clock.now(),
        )
        async with self.d.uow() as uow:
            uow.transcripts.add(t)
            await uow.commit()
        return TranscriptDetail.of(t)


def split_into_segments(text: str) -> list[str]:
    """One segment per non-empty line; lines over the segment limit are split at word boundaries."""
    out: list[str] = []
    for line in text.splitlines():
        line = " ".join(line.split())
        while len(line) > SEGMENT_MAX:
            cut = line.rfind(" ", 0, SEGMENT_MAX)
            cut = cut if cut > 0 else SEGMENT_MAX
            out.append(line[:cut])
            line = line[cut:].strip()
        if line:
            out.append(line)
    return out


@dataclass(frozen=True)
class RenameTranscript:
    transcript_id: UUID
    title: str
    expected_version: int | None
    tenant_id: TenantId = PUBLIC_TENANT


class RenameTranscriptHandler:
    def __init__(self, deps: Deps) -> None:
        self.d = deps

    async def execute(self, cmd: RenameTranscript) -> TranscriptDetail:
        title = Title(cmd.title)
        async with self.d.uow() as uow:
            t = await _load(uow, cmd.tenant_id, cmd.transcript_id)
            _check_version(t, cmd.expected_version)
            t.rename(title, now=self.d.clock.now())
            await uow.commit()
        return TranscriptDetail.of(t)


@dataclass(frozen=True)
class EditSegment:
    transcript_id: UUID
    seq: int
    text: str
    expected_version: int | None
    tenant_id: TenantId = PUBLIC_TENANT


class EditSegmentHandler:
    def __init__(self, deps: Deps) -> None:
        self.d = deps

    async def execute(self, cmd: EditSegment) -> TranscriptDetail:
        text = SegmentText(cmd.text)
        async with self.d.uow() as uow:
            t = await _load(uow, cmd.tenant_id, cmd.transcript_id)
            _check_version(t, cmd.expected_version)
            t.edit_segment(cmd.seq, text, self.d.tag(text.value), now=self.d.clock.now())
            await uow.commit()
        return TranscriptDetail.of(t)


@dataclass(frozen=True)
class DeleteTranscript:
    transcript_id: UUID
    hard: bool = False
    expected_version: int | None = None
    tenant_id: TenantId = PUBLIC_TENANT


class DeleteTranscriptHandler:
    def __init__(self, deps: Deps) -> None:
        self.d = deps

    async def execute(self, cmd: DeleteTranscript) -> None:
        async with self.d.uow() as uow:
            # A hard delete may target a transcript that is already soft-deleted.
            t = await _load(uow, cmd.tenant_id, cmd.transcript_id, include_deleted=cmd.hard)
            _check_version(t, cmd.expected_version)
            if cmd.hard:
                t.mark_hard_deleted()
                uow.transcripts.remove(t)
            else:
                t.soft_delete(now=self.d.clock.now())
            await uow.commit()


@dataclass(frozen=True)
class RestoreTranscript:
    transcript_id: UUID
    tenant_id: TenantId = PUBLIC_TENANT


class RestoreTranscriptHandler:
    def __init__(self, deps: Deps) -> None:
        self.d = deps

    async def execute(self, cmd: RestoreTranscript) -> TranscriptDetail:
        async with self.d.uow() as uow:
            t = await _load(uow, cmd.tenant_id, cmd.transcript_id, include_deleted=True)
            t.restore(now=self.d.clock.now())
            await uow.commit()
        return TranscriptDetail.of(t)


# --- queries --------------------------------------------------------------------------------------


MAX_PAGE = 100


class SearchTranscripts:
    def __init__(self, read_model: TranscriptReadModel) -> None:
        self.rm = read_model

    async def execute(self, query: SearchQuery, tenant_id: TenantId = PUBLIC_TENANT) -> Page:
        if not 1 <= query.limit <= MAX_PAGE:
            raise InvalidValue(f"limit must be between 1 and {MAX_PAGE}.", field="limit")
        return await self.rm.search(tenant_id, query)


class GetTranscript:
    def __init__(self, read_model: TranscriptReadModel) -> None:
        self.rm = read_model

    async def execute(self, id: UUID, tenant_id: TenantId = PUBLIC_TENANT) -> TranscriptDetail:
        detail = await self.rm.get(tenant_id, id)
        if detail is None:
            raise TranscriptNotFound("Transcript not found.")
        return detail


class ExportTranscript:
    def __init__(self, read_model: TranscriptReadModel) -> None:
        self.rm = read_model

    async def execute(self, id: UUID, tenant_id: TenantId = PUBLIC_TENANT) -> tuple[str, str]:
        """Returns (filename, plain text)."""
        d = await GetTranscript(self.rm).execute(id, tenant_id)
        s = d.summary
        header = [s.title, f"{s.created_at:%Y-%m-%d %H:%M} UTC · engine: {s.engine}"]
        if s.hindi_ratio is not None:
            header.append(f"Hindi share: {round(s.hindi_ratio * 100)}%")
        body = "\n".join(seg.text for seg in d.segments)
        slug = "".join(c if c.isalnum() else "-" for c in s.title.lower()).strip("-")[:50] or "transcript"
        return f"{slug}.txt", "\n".join(header) + "\n\n" + body + "\n"
