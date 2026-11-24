"""LiveSession: one streaming connection that writes into a transcript. A transcript can have several
(one per reconnect/resume)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class SessionState(StrEnum):
    STREAMING = "streaming"
    ENDED = "ended"


@dataclass
class LiveSession:
    id: UUID
    transcript_id: UUID
    engine: str
    started_at: datetime
    state: SessionState = SessionState.STREAMING
    ended_at: datetime | None = None
    close_reason: str | None = None
    first_partial_ms: int | None = None
    segments: int = 0

    def record_segment(self) -> None:
        self.segments += 1

    def end(self, *, reason: str, now: datetime, first_partial_ms: int | None) -> None:
        if self.state is SessionState.ENDED:
            return
        self.state = SessionState.ENDED
        self.ended_at = now
        self.close_reason = reason[:40]
        self.first_partial_ms = first_partial_ms

    @property
    def duration_ms(self) -> int | None:
        if self.ended_at is None:
            return None
        return max(0, int((self.ended_at - self.started_at).total_seconds() * 1000))
