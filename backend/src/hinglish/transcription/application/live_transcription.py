"""Use cases of a live session (ARCHITECTURE §8: StartLiveSession, HandleRecognizerEvent, StopLiveSession).

Partials never touch the database. Each final is appended to the transcript in its own transaction
before it is sent to the client, so what the user sees as final is already saved (FR-2).
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import structlog

from hinglish.shared_kernel import Clock, new_id
from hinglish.transcription.application.ports.live_sessions import LiveSessionRepository
from hinglish.transcription.domain.live_session import LiveSession
from hinglish.transcripts.api import (
    AppendFinal,
    CompleteRecording,
    InvalidStateTransition,
    ResumeRecording,
    SegmentView,
    StartRecording,
    TranscriptNotFound,
    TranscriptsModule,
)

log = structlog.get_logger()


@dataclass(frozen=True, slots=True)
class LiveHandle:
    session_id: UUID
    transcript_id: UUID
    last_seq: int
    resumed: bool


class LiveTranscription:
    def __init__(self, transcripts: TranscriptsModule, sessions: LiveSessionRepository, clock: Clock) -> None:
        self._t = transcripts
        self._sessions = sessions
        self._clock = clock
        self._live: dict[UUID, LiveSession] = {}

    async def start(
        self, *, engine: str, script: str, model_id: str | None, resume_transcript_id: UUID | None
    ) -> LiveHandle:
        handle = None
        if resume_transcript_id is not None:
            try:
                handle = await self._t.resume_recording.execute(ResumeRecording(resume_transcript_id))
            except (TranscriptNotFound, InvalidStateTransition):
                log.info("live.resume_unavailable", transcript_id=str(resume_transcript_id))
        resumed = handle is not None
        if handle is None:
            handle = await self._t.start_recording.execute(
                StartRecording(engine=engine, script=script, model_id=model_id)
            )
        session = LiveSession(
            id=new_id(), transcript_id=handle.transcript_id, engine=engine, started_at=self._clock.now()
        )
        await self._sessions.save(session)
        self._live[session.id] = session
        return LiveHandle(
            session_id=session.id,
            transcript_id=handle.transcript_id,
            last_seq=handle.last_seq,
            resumed=resumed,
        )

    async def record_final(self, handle: LiveHandle, *, text: str, language: str | None) -> SegmentView:
        seg = await self._t.append_final.execute(
            AppendFinal(transcript_id=handle.transcript_id, text=text, language=language)
        )
        if (session := self._live.get(handle.session_id)) is not None:
            session.record_segment()
        return seg

    async def finish(self, handle: LiveHandle, *, reason: str, first_partial_ms: int | None) -> None:
        """Ends the session and completes the transcript (a later resume reopens it)."""
        session = self._live.pop(handle.session_id, None)
        duration_ms = None
        if session is not None:
            session.end(reason=reason, now=self._clock.now(), first_partial_ms=first_partial_ms)
            duration_ms = session.duration_ms
            await self._sessions.save(session)
        await self._t.complete_recording.execute(
            CompleteRecording(transcript_id=handle.transcript_id, duration_ms=duration_ms)
        )
