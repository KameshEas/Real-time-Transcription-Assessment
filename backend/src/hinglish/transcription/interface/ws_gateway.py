"""Realtime gateway: `/ws/v1/transcribe` (protocol v1, see protocol_v1.py).

Per connection, three tasks:
  uplink   client -> recognizer   (binary PCM frames, stop, ping; enforces idle + max-duration limits)
  downlink recognizer -> buffer   (partials are droppable, finals never are)
  writer   buffer -> client
The gateway holds no business rules beyond transport mapping; persistence of finals arrives with the
Transcripts context (Day 2).
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Mapping
from typing import Literal, cast, get_args
from uuid import uuid4

import structlog
from fastapi import APIRouter, WebSocket
from pydantic import ValidationError
from starlette.websockets import WebSocketDisconnect, WebSocketState

from hinglish.transcription.application.outbound_buffer import Outbound, OutboundBuffer
from hinglish.transcription.application.ports.speech_recognizer import (
    RecognizerConfig,
    RecognizerSession,
    RecognizerUnavailable,
    SpeechRecognizer,
)
from hinglish.transcription.domain.session_policy import SessionPolicy
from hinglish.transcription.interface.protocol_v1 import (
    DoneMsg,
    ErrorCode,
    ErrorMsg,
    FinalMsg,
    LatencyMsg,
    LimitMsg,
    PartialMsg,
    PingMsg,
    PongMsg,
    ReadyMsg,
    ServerMsg,
    StartMsg,
    StopMsg,
    client_msg_adapter,
)

log = structlog.get_logger()
router = APIRouter()


def as_error_code(code: str | None) -> ErrorCode:
    """Vendor adapters report string codes; anything unknown becomes ENGINE_ERROR."""
    return cast(ErrorCode, code) if code in get_args(ErrorCode) else "ENGINE_ERROR"


UplinkEnd = Literal["stopped", "limit", "idle", "disconnect"]
DRAIN_TIMEOUT_S = 15.0  # time allowed for the engine to finalize after stop


@router.websocket("/ws/v1/transcribe")
async def transcribe(ws: WebSocket) -> None:
    state = ws.app.state
    origin = ws.headers.get("origin")
    allowed: list[str] = state.settings.cors_origins
    if origin and "*" not in allowed and origin not in allowed:
        await ws.close(code=1008, reason="origin not allowed")
        return
    await ws.accept()
    await LiveConnection(ws, state.recognizers, state.session_policy).run()


class LiveConnection:
    def __init__(
        self, ws: WebSocket, recognizers: Mapping[str, SpeechRecognizer], policy: SessionPolicy
    ) -> None:
        self.ws = ws
        self.recognizers = recognizers
        self.policy = policy
        self.out = OutboundBuffer(capacity=64)
        self.session_id = str(uuid4())
        self.log = log.bind(session_id=self.session_id)
        self.started_at = 0.0
        self.first_audio_at: float | None = None
        self.first_partial_sent = False
        self.segments = 0
        self.client_gone = False
        self.engine_error = False

    # --- lifecycle ------------------------------------------------------------------------------

    async def run(self) -> None:
        start = await self._await_start()
        if start is None:
            return
        recognizer = self.recognizers.get(start.engine)
        if recognizer is None:
            await self._fail(
                "ENGINE_NOT_AVAILABLE", f"Engine '{start.engine}' is not available on this server."
            )
            return
        try:
            session = await recognizer.open(RecognizerConfig(script=start.script))
        except RecognizerUnavailable as exc:
            self.log.warning("live.engine_open_failed", code=exc.code)
            await self._fail(
                as_error_code(exc.code), "Transcription service unavailable.", retryable=exc.retryable
            )
            return

        self.started_at = time.monotonic()
        self.log.info("live.started", engine=start.engine, script=start.script)
        self._send(
            ReadyMsg(
                session_id=self.session_id,
                engine=start.engine,
                script=start.script,
                max_duration_s=self.policy.max_duration_s,
            )
        )
        writer = asyncio.create_task(self._writer())
        uplink = asyncio.create_task(self._uplink(session))
        downlink = asyncio.create_task(self._downlink(session))

        try:
            await asyncio.wait({uplink, downlink}, return_when=asyncio.FIRST_COMPLETED)
            reason = await self._wind_down(session, uplink, downlink)
        finally:
            for task in (uplink, downlink):
                task.cancel()
            await session.abort()

        if not self.client_gone:
            self._send(
                DoneMsg(
                    reason=reason,
                    segments=self.segments,
                    duration_ms=int((time.monotonic() - self.started_at) * 1000),
                    dropped_partials=self.out.dropped,
                )
            )
        self.out.close()
        await writer
        await self._close_socket()
        self.log.info("live.ended", reason=reason, segments=self.segments, dropped=self.out.dropped)

    async def _wind_down(
        self, session: RecognizerSession, uplink: asyncio.Task[UplinkEnd], downlink: asyncio.Task[None]
    ) -> Literal["stopped", "limit", "engine_closed", "error", "idle"]:
        if not uplink.done():  # the engine ended first (fatal error or vendor close)
            uplink.cancel()
            return "error" if self.engine_error else "engine_closed"
        ended = uplink.result()
        if ended == "disconnect":
            self.client_gone = True
            return "stopped"
        # Graceful: let the engine finalize the pending utterance, then drain its events.
        await session.close()
        with contextlib.suppress(TimeoutError):
            async with asyncio.timeout(DRAIN_TIMEOUT_S):
                await downlink
        return ended

    async def _await_start(self) -> StartMsg | None:
        try:
            async with asyncio.timeout(self.policy.start_timeout_s):
                raw = await self.ws.receive_text()
            msg = client_msg_adapter.validate_json(raw)
        except TimeoutError:
            await self._fail("START_REQUIRED", "Send a start message first.")
            return None
        except (ValidationError, KeyError):
            await self._fail("BAD_MESSAGE", "The first message must be a valid v1 start message.")
            return None
        except WebSocketDisconnect:
            return None
        if not isinstance(msg, StartMsg):
            await self._fail("START_REQUIRED", "Send a start message first.")
            return None
        return msg

    # --- tasks ----------------------------------------------------------------------------------

    async def _uplink(self, session: RecognizerSession) -> UplinkEnd:
        bad_frame_reported = False
        while True:
            elapsed = time.monotonic() - self.started_at
            remaining = self.policy.max_duration_s - elapsed
            # Decide which deadline is armed up front: timers can fire a few ms early, so re-reading
            # the clock after a timeout could mislabel the session limit as an idle timeout.
            limit_is_next = remaining <= self.policy.idle_timeout_s
            if remaining <= 0:
                self._send(LimitMsg(max_duration_s=self.policy.max_duration_s))
                return "limit"
            try:
                async with asyncio.timeout(remaining if limit_is_next else self.policy.idle_timeout_s):
                    message = await self.ws.receive()
            except TimeoutError:
                if limit_is_next:
                    self._send(LimitMsg(max_duration_s=self.policy.max_duration_s))
                    return "limit"
                self._send(
                    ErrorMsg(code="IDLE_TIMEOUT", message="No audio received for a while.", fatal=True)
                )
                return "idle"

            if message["type"] == "websocket.disconnect":
                return "disconnect"
            if (frame := message.get("bytes")) is not None:
                if not self.policy.frame_is_valid(frame):
                    if not bad_frame_reported:
                        bad_frame_reported = True
                        self._send(
                            ErrorMsg(code="FRAME_INVALID", message="Audio frame rejected.", fatal=False)
                        )
                    continue
                if self.first_audio_at is None:
                    self.first_audio_at = time.monotonic()
                await session.send_audio(frame)
            elif (text := message.get("text")) is not None:
                try:
                    msg = client_msg_adapter.validate_json(text)
                except ValidationError:
                    self._send(ErrorMsg(code="BAD_MESSAGE", message="Unknown message.", fatal=False))
                    continue
                if isinstance(msg, StopMsg):
                    return "stopped"
                if isinstance(msg, PingMsg):
                    self._send(PongMsg())

    async def _downlink(self, session: RecognizerSession) -> None:
        async for event in session.events():
            if event.kind == "partial":
                if not event.text:
                    continue
                if not self.first_partial_sent and self.first_audio_at is not None:
                    self.first_partial_sent = True
                    ms = int((time.monotonic() - self.first_audio_at) * 1000)
                    self._send(LatencyMsg(first_partial_ms=ms))
                    self.log.info("live.first_partial", ms=ms)
                self.out.put(
                    Outbound(PartialMsg(utterance=event.utterance, text=event.text).model_dump(), True)
                )
            elif event.kind == "final":
                if not event.text.strip():
                    continue
                self.segments += 1
                self._send(
                    FinalMsg(
                        seq=self.segments, utterance=event.utterance, text=event.text, language=event.language
                    )
                )
            else:
                self._send(
                    ErrorMsg(
                        code=as_error_code(event.error_code),
                        message="Transcription service error." if event.fatal else "Transcription warning.",
                        fatal=event.fatal,
                        retryable=event.retryable,
                    )
                )
                if event.fatal:
                    self.engine_error = True
                    return

    async def _writer(self) -> None:
        while (item := await self.out.get()) is not None:
            if self.client_gone:
                continue
            try:
                await self.ws.send_json(item.payload)
            except (WebSocketDisconnect, RuntimeError):
                self.client_gone = True

    # --- helpers --------------------------------------------------------------------------------

    def _send(self, msg: ServerMsg) -> None:
        self.out.put(Outbound(msg.model_dump()))

    async def _fail(self, code: ErrorCode, message: str, *, retryable: bool = False) -> None:
        with contextlib.suppress(WebSocketDisconnect, RuntimeError):
            await self.ws.send_json(ErrorMsg(code=code, message=message, retryable=retryable).model_dump())
        await self._close_socket()

    async def _close_socket(self) -> None:
        if self.ws.client_state == WebSocketState.CONNECTED:
            with contextlib.suppress(RuntimeError):
                await self.ws.close(code=1000)
