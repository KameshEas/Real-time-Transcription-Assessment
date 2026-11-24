"""Composition root: the only module that knows concrete adapters. Wires ports by settings."""

from __future__ import annotations

from dataclasses import dataclass

from hinglish.bootstrap.settings import Settings
from hinglish.shared_kernel import Clock, SystemClock
from hinglish.transcription.application.ports.speech_recognizer import SpeechRecognizer
from hinglish.transcription.infrastructure.fake_recognizer import FakeRecognizer


@dataclass
class Container:
    settings: Settings
    clock: Clock
    recognizer: SpeechRecognizer


def build_container(settings: Settings) -> Container:
    # TODO(Day 1): swap in SarvamRealtimeRecognizer when enable_sarvam and a key is present.
    recognizer: SpeechRecognizer = FakeRecognizer()
    return Container(settings=settings, clock=SystemClock(), recognizer=recognizer)
