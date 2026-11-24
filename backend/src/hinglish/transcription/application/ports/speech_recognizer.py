"""Port: a streaming speech-to-text session. Implemented by vendor adapters in infrastructure."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal, Protocol

ScriptMode = Literal["mixed", "devanagari", "roman"]


class RecognizerUnavailable(Exception):
    """The vendor could not open a session (bad key, quota, outage). `code` maps to protocol error codes."""

    def __init__(self, message: str, *, code: str = "ENGINE_UNAVAILABLE", retryable: bool = True) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class RecognizerConfig:
    script: ScriptMode = "mixed"
    sample_rate: int = 16_000


@dataclass(frozen=True, slots=True)
class RecognizerEvent:
    kind: Literal["partial", "final", "error"]
    text: str = ""
    utterance: int = 0
    language: str | None = None
    error_code: str | None = None
    fatal: bool = False
    retryable: bool = True


class RecognizerSession(Protocol):
    async def send_audio(self, pcm16: bytes) -> None:
        """Send one mono 16-bit little-endian PCM frame (~100 ms)."""
        ...

    async def close(self) -> None:
        """Finish gracefully: pending audio is finalized, then `events()` ends."""
        ...

    async def abort(self) -> None:
        """Tear down immediately (client vanished). Safe to call more than once."""
        ...

    def events(self) -> AsyncIterator[RecognizerEvent]: ...


class SpeechRecognizer(Protocol):
    name: str

    async def open(self, config: RecognizerConfig) -> RecognizerSession:
        """Open a session. Raises `RecognizerUnavailable` when the vendor rejects or is unreachable."""
        ...
