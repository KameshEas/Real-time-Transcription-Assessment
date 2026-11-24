"""Realtime protocol v1 for `/ws/v1/transcribe`. Every JSON message carries `"v": 1`; audio frames are binary
(mono PCM16 little-endian, 16 kHz, ~100 ms per frame).

Client -> server: start, <binary frames>, stop, ping
Server -> client: ready, partial, final, latency, limit, error, done, pong
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from hinglish.transcription.application.ports.speech_recognizer import ScriptMode

PROTOCOL_VERSION = 1


class _Msg(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    v: Literal[1] = 1


# --- client -> server ---------------------------------------------------------------------------


class StartMsg(_Msg):
    type: Literal["start"]
    engine: str = "sarvam"
    script: ScriptMode = "mixed"
    resume_transcript_id: str | None = None
    passcode: str | None = None


class StopMsg(_Msg):
    type: Literal["stop"]


class PingMsg(_Msg):
    type: Literal["ping"]


ClientMsg = Annotated[StartMsg | StopMsg | PingMsg, Field(discriminator="type")]
client_msg_adapter: TypeAdapter[StartMsg | StopMsg | PingMsg] = TypeAdapter(ClientMsg)


# --- server -> client ---------------------------------------------------------------------------


class ReadyMsg(_Msg):
    type: Literal["ready"] = "ready"
    session_id: str
    engine: str
    script: ScriptMode
    max_duration_s: float


class PartialMsg(_Msg):
    type: Literal["partial"] = "partial"
    utterance: int
    text: str


class FinalMsg(_Msg):
    type: Literal["final"] = "final"
    seq: int
    utterance: int
    text: str
    language: str | None = None


class LatencyMsg(_Msg):
    type: Literal["latency"] = "latency"
    first_partial_ms: int


class LimitMsg(_Msg):
    type: Literal["limit"] = "limit"
    reason: Literal["max_duration"] = "max_duration"
    max_duration_s: float


ErrorCode = Literal[
    "BAD_MESSAGE",
    "START_REQUIRED",
    "FRAME_INVALID",
    "FRAME_TOO_LARGE",
    "IDLE_TIMEOUT",
    "ENGINE_NOT_AVAILABLE",
    "ENGINE_UNAVAILABLE",
    "ENGINE_AUTH",
    "ENGINE_QUOTA",
    "ENGINE_CONFIG",
    "ENGINE_IDLE_TIMEOUT",
    "ENGINE_ERROR",
]


class ErrorMsg(_Msg):
    type: Literal["error"] = "error"
    code: ErrorCode
    message: str
    fatal: bool = True
    retryable: bool = False


class DoneMsg(_Msg):
    type: Literal["done"] = "done"
    reason: Literal["stopped", "limit", "engine_closed", "error", "idle"]
    segments: int
    duration_ms: int
    dropped_partials: int


class PongMsg(_Msg):
    type: Literal["pong"] = "pong"


ServerMsg = ReadyMsg | PartialMsg | FinalMsg | LatencyMsg | LimitMsg | ErrorMsg | DoneMsg | PongMsg
