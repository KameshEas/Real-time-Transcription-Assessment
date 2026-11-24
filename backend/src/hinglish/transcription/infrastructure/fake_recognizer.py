"""Deterministic recognizer for tests, CI, local dev without keys, and load tests. No network, no AI.

Every `FRAMES_PER_STEP` frames it grows the current utterance by one phrase (a partial); after the
last phrase it emits a final and starts the next utterance. `close()` finalizes a pending utterance.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from hinglish.transcription.application.ports.speech_recognizer import (
    RecognizerConfig,
    RecognizerEvent,
)

PHRASES = ["aaj ki meeting", "mein hum budget", "discuss karenge"]
FRAMES_PER_STEP = 5  # ~500 ms of 100 ms frames per emitted event


class FakeRecognizerSession:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[RecognizerEvent | None] = asyncio.Queue()
        self._frames = 0
        self._words: list[str] = []
        self._utterance = 0
        self._closed = False

    async def send_audio(self, pcm16: bytes) -> None:
        if self._closed:
            return
        self._frames += 1
        if self._frames % FRAMES_PER_STEP:
            return
        self._words.append(PHRASES[len(self._words)])
        if len(self._words) == len(PHRASES):
            self._emit_final()
        else:
            self._queue.put_nowait(
                RecognizerEvent(kind="partial", text=self._text, utterance=self._utterance)
            )

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._words:
            self._emit_final()
        self._queue.put_nowait(None)

    async def abort(self) -> None:
        self._closed = True
        self._queue.put_nowait(None)

    async def events(self) -> AsyncIterator[RecognizerEvent]:
        while (event := await self._queue.get()) is not None:
            yield event

    @property
    def _text(self) -> str:
        return " ".join(self._words)

    def _emit_final(self) -> None:
        self._queue.put_nowait(RecognizerEvent(kind="final", text=self._text, utterance=self._utterance))
        self._words = []
        self._utterance += 1


class FakeRecognizer:
    name = "fake"

    async def open(self, config: RecognizerConfig) -> FakeRecognizerSession:
        return FakeRecognizerSession()
