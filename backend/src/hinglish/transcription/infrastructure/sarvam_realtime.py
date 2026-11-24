"""Sarvam `saaras:v4` Realtime adapter for the SpeechRecognizer port.

Spike (24 Nov 2026, Bulbul-generated Hinglish clips): `stream_type=fast` gives the first partial in
~0.75 s; `codemix` keeps English words in Latin script inside Devanagari Hindi, `translit` returns
fully Romanized text, `transcribe` writes everything (English too) in Devanagari.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack
from typing import Any

import structlog
from sarvamai import AsyncSarvamAI
from sarvamai.core.api_error import ApiError
from sarvamai.types.realtime_audio_input import RealtimeAudioInput
from sarvamai.types.realtime_end import RealtimeEnd
from sarvamai.types.realtime_error import RealtimeError
from sarvamai.types.realtime_session_end import RealtimeSessionEnd
from sarvamai.types.realtime_transcript_final import RealtimeTranscriptFinal
from sarvamai.types.realtime_transcript_partial import RealtimeTranscriptPartial
from websockets.exceptions import ConnectionClosed

from hinglish.transcription.application.ports.speech_recognizer import (
    RecognizerConfig,
    RecognizerEvent,
    RecognizerUnavailable,
    ScriptMode,
)

log = structlog.get_logger()

# Our script choice -> Sarvam `mode`. `mode` applies to finals; partials are always plain transcription.
SCRIPT_TO_MODE: dict[ScriptMode, str] = {
    "mixed": "codemix",
    "roman": "translit",
    "devanagari": "transcribe",
}

# WebSocket close codes documented by Sarvam -> (protocol error code, retryable)
CLOSE_CODES: dict[int, tuple[str, bool]] = {
    1003: ("ENGINE_QUOTA", False),  # rate limit, quota exhausted or invalid key
    1008: ("ENGINE_IDLE_TIMEOUT", True),
    1011: ("ENGINE_ERROR", True),
    4000: ("ENGINE_CONFIG", False),
}

VENDOR_ERROR_CODES: dict[str, str] = {
    "invalid_subscription_key": "ENGINE_AUTH",
    "inactivity_timeout": "ENGINE_IDLE_TIMEOUT",
    "chunk_too_large": "FRAME_TOO_LARGE",
    "invalid_request": "ENGINE_CONFIG",
    "invalid_model": "ENGINE_CONFIG",
}

CONNECT_TIMEOUT_S = 10.0
FINALIZE_TIMEOUT_S = 10.0


class SarvamRealtimeSession:
    def __init__(self, socket: Any, stack: AsyncExitStack) -> None:
        self._socket = socket
        self._stack = stack
        self._closing = False
        self._closed = False

    async def send_audio(self, pcm16: bytes) -> None:
        if self._closing:
            return
        audio = base64.b64encode(pcm16).decode("ascii")
        try:
            await self._socket.send_realtime_audio_input(RealtimeAudioInput(audio=audio))
        except ConnectionClosed:
            self._closing = True  # surfaced to the client through `events()`

    async def close(self) -> None:
        if self._closing:
            return
        self._closing = True
        with contextlib.suppress(ConnectionClosed):
            await self._socket.send_realtime_end(RealtimeEnd())

    async def abort(self) -> None:
        self._closing = True
        if not self._closed:
            self._closed = True
            with contextlib.suppress(Exception):
                await self._stack.aclose()

    async def events(self) -> AsyncIterator[RecognizerEvent]:
        try:
            while True:
                # Once `end` is sent, don't wait forever for the vendor to finalize.
                timeout = FINALIZE_TIMEOUT_S if self._closing else None
                try:
                    async with asyncio.timeout(timeout):
                        msg = await self._socket.recv()
                except TimeoutError:
                    log.warning("sarvam.finalize_timeout")
                    return
                event = _map_message(msg)
                if event is not None:
                    yield event
                if isinstance(msg, RealtimeSessionEnd) or (event is not None and event.fatal):
                    return
        except ConnectionClosed as exc:
            code = exc.rcvd.code if exc.rcvd else None
            if code is not None and code != 1000:
                mapped, retryable = CLOSE_CODES.get(code, ("ENGINE_ERROR", True))
                log.warning("sarvam.closed", close_code=code)
                yield RecognizerEvent(kind="error", error_code=mapped, fatal=True, retryable=retryable)
        finally:
            await self.abort()


def _map_message(msg: Any) -> RecognizerEvent | None:
    if isinstance(msg, RealtimeTranscriptPartial):
        return RecognizerEvent(
            kind="partial", text=msg.text, utterance=msg.utterance_idx, language=msg.language
        )
    if isinstance(msg, RealtimeTranscriptFinal):
        return RecognizerEvent(
            kind="final", text=msg.text, utterance=msg.utterance_idx, language=msg.language
        )
    if isinstance(msg, RealtimeError):
        log.warning("sarvam.error", code=msg.code, fatal=msg.is_fatal, status=msg.status_code)
        code = VENDOR_ERROR_CODES.get(msg.code, "ENGINE_ERROR")
        retryable = code not in ("ENGINE_AUTH", "ENGINE_CONFIG")
        return RecognizerEvent(kind="error", error_code=code, fatal=msg.is_fatal, retryable=retryable)
    return None  # session.begin, vad events, pong, config.updated


class SarvamRealtimeRecognizer:
    name = "sarvam"

    def __init__(self, api_key: str, *, model: str = "saaras:v4", stream_type: str = "fast") -> None:
        self._client = AsyncSarvamAI(api_subscription_key=api_key)
        self._model = model
        self._stream_type = stream_type
        self.model = model  # recorded on transcripts as model_id

    async def open(self, config: RecognizerConfig) -> SarvamRealtimeSession:
        stack = AsyncExitStack()
        try:
            async with asyncio.timeout(CONNECT_TIMEOUT_S):
                socket = await stack.enter_async_context(
                    self._client.speech_to_text_realtime_streaming.connect(
                        language_code="auto",
                        model=self._model,
                        mode=SCRIPT_TO_MODE[config.script],
                        stream_type=self._stream_type,
                        encoding="linear16",
                        sample_rate=str(config.sample_rate),
                    )
                )
        except ApiError as exc:
            await stack.aclose()
            if exc.status_code in (401, 403):
                raise RecognizerUnavailable(
                    "Sarvam rejected the API key", code="ENGINE_AUTH", retryable=False
                ) from exc
            raise RecognizerUnavailable(f"Sarvam returned {exc.status_code}") from exc
        except (TimeoutError, OSError) as exc:
            await stack.aclose()
            raise RecognizerUnavailable("Sarvam is unreachable") from exc
        return SarvamRealtimeSession(socket, stack)
