"""Validated, immutable values of the Transcripts context."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from hinglish.transcripts.domain.errors import InvalidValue

TITLE_MAX = 200
SEGMENT_MAX = 5_000
MANUAL_TEXT_MAX = 100_000


class ScriptMode(StrEnum):
    MIXED = "mixed"
    DEVANAGARI = "devanagari"
    ROMAN = "roman"


class Engine(StrEnum):
    SARVAM = "sarvam"
    MANUAL = "manual"
    FAKE = "fake"  # offline demo / tests


class TranscriptStatus(StrEnum):
    RECORDING = "recording"
    COMPLETED = "completed"


@dataclass(frozen=True, slots=True)
class Title:
    value: str

    def __post_init__(self) -> None:
        cleaned = " ".join(self.value.split())
        if not cleaned:
            raise InvalidValue("Title can't be empty.", field="title")
        if len(cleaned) > TITLE_MAX:
            raise InvalidValue(f"Title must be at most {TITLE_MAX} characters.", field="title")
        object.__setattr__(self, "value", cleaned)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class SegmentText:
    value: str

    def __post_init__(self) -> None:
        cleaned = self.value.strip()
        if not cleaned:
            raise InvalidValue("Segment text can't be empty.", field="text")
        if len(cleaned) > SEGMENT_MAX:
            raise InvalidValue(f"Segment text must be at most {SEGMENT_MAX} characters.", field="text")
        object.__setattr__(self, "value", cleaned)

    def __str__(self) -> str:
        return self.value
