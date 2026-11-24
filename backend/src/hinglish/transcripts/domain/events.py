"""Domain events raised by the Transcript aggregate. Written to the outbox in the same transaction."""

from __future__ import annotations

from dataclasses import dataclass

from hinglish.shared_kernel import DomainEvent


@dataclass(frozen=True, kw_only=True)
class TranscriptCreated(DomainEvent):
    engine: str


@dataclass(frozen=True, kw_only=True)
class SegmentFinalized(DomainEvent):
    seq: int


@dataclass(frozen=True, kw_only=True)
class TranscriptCompleted(DomainEvent):
    duration_ms: int | None


@dataclass(frozen=True, kw_only=True)
class TranscriptEdited(DomainEvent):
    what: str  # "title" | "segment"
    seq: int | None = None


@dataclass(frozen=True, kw_only=True)
class TranscriptDeleted(DomainEvent):
    hard: bool


@dataclass(frozen=True, kw_only=True)
class TranscriptRestored(DomainEvent):
    pass
