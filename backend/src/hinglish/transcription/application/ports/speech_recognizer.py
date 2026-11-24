"""Port: a streaming speech-to-text session. Implemented by vendor adapters in infrastructure."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal, Protocol

ScriptMode = Literal["mixed", "devanagari", "roman"]


@dataclass(frozen=True, slots=True)
class RecognizerConfig:
    script: ScriptMode = "mixed"
    sample_rate: int = 16_000


@dataclass(frozen=True, slots=True)
class RecognizerEvent:
    kind: Literal["partial", "final", "error"]
    text: str = ""
    start_ms: int | None = None
    end_ms: int | None = None
    error_code: str | None = None


class RecognizerSession(Protocol):
    async def send_audio(self, pcm16: bytes) -> None: ...
    async def close(self) -> None: ...
    def events(self) -> AsyncIterator[RecognizerEvent]: ...


class SpeechRecognizer(Protocol):
    name: str

    async def open(self, config: RecognizerConfig) -> RecognizerSession: ...
