"""Deterministic recognizer for tests, CI and load tests. No network, no AI."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from hinglish.transcription.application.ports.speech_recognizer import (
    RecognizerConfig,
    RecognizerEvent,
)

_SCRIPT = ["aaj ki meeting", "aaj ki meeting mein hum", "aaj ki meeting mein hum budget discuss karenge"]
_FRAMES_PER_STEP = 5  # ~500 ms of 100 ms frames per emitted event


class FakeRecognizerSession:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[RecognizerEvent | None] = asyncio.Queue()
        self._frames = 0
        self._step = 0

    async def send_audio(self, pcm16: bytes) -> None:
        self._frames += 1
        if self._frames % _FRAMES_PER_STEP:
            return
        text = _SCRIPT[self._step % len(_SCRIPT)]
        is_final = self._step % len(_SCRIPT) == len(_SCRIPT) - 1
        await self._queue.put(RecognizerEvent(kind="final" if is_final else "partial", text=text))
        self._step += 1

    async def close(self) -> None:
        await self._queue.put(None)

    async def events(self) -> AsyncIterator[RecognizerEvent]:
        while (event := await self._queue.get()) is not None:
            yield event


class FakeRecognizer:
    name = "fake"

    async def open(self, config: RecognizerConfig) -> FakeRecognizerSession:
        return FakeRecognizerSession()
