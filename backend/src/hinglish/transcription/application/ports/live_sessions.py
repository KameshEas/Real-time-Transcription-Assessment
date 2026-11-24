from __future__ import annotations

from typing import Protocol

from hinglish.transcription.domain.live_session import LiveSession


class LiveSessionRepository(Protocol):
    async def save(self, session: LiveSession) -> None:
        """Insert or update the session row."""
        ...
