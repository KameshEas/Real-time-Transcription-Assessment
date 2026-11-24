"""Composition root: the only module that knows concrete adapters. Wires ports by settings."""

from __future__ import annotations

from dataclasses import dataclass, field

from hinglish.bootstrap.settings import Settings
from hinglish.shared_kernel import Clock, SystemClock
from hinglish.transcription.application.ports.speech_recognizer import SpeechRecognizer
from hinglish.transcription.domain.session_policy import SessionPolicy
from hinglish.transcription.infrastructure.fake_recognizer import FakeRecognizer
from hinglish.transcription.infrastructure.sarvam_realtime import SarvamRealtimeRecognizer


@dataclass
class Container:
    settings: Settings
    clock: Clock
    session_policy: SessionPolicy
    recognizers: dict[str, SpeechRecognizer] = field(default_factory=dict)


def build_recognizers(settings: Settings) -> dict[str, SpeechRecognizer]:
    """Engines a client may pick in `start.engine`. The fake engine is never offered in production."""
    recognizers: dict[str, SpeechRecognizer] = {}
    if settings.enable_sarvam and settings.sarvam_api_key is not None:
        recognizers["sarvam"] = SarvamRealtimeRecognizer(
            settings.sarvam_api_key.get_secret_value(),
            model=settings.sarvam_stt_model,
            stream_type=settings.sarvam_stream_type,
        )
    if settings.use_fake_recognizer or settings.app_env != "production":
        recognizers["fake"] = FakeRecognizer()
    return recognizers


def build_container(settings: Settings) -> Container:
    return Container(
        settings=settings,
        clock=SystemClock(),
        session_policy=SessionPolicy(max_duration_s=float(settings.max_session_seconds)),
        recognizers=build_recognizers(settings),
    )
