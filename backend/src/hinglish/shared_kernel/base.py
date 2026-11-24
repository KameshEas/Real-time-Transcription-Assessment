"""Base building blocks for domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID


class DomainError(Exception):
    """Raised when a domain invariant is violated. `code` is stable and maps to Problem Details."""

    code: str = "DOMAIN_ERROR"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code:
            self.code = code


@dataclass(frozen=True, slots=True)
class ValueObject:
    """Immutable, compared by value. Subclasses validate in `__post_init__`."""


@dataclass(frozen=True, kw_only=True)
class DomainEvent:
    aggregate_id: UUID
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def type(self) -> str:
        return type(self).__name__


class Entity:
    """Identity-based equality plus a buffer of pending domain events."""

    def __init__(self, id: UUID) -> None:
        self.id = id
        self._events: list[DomainEvent] = []

    def record(self, event: DomainEvent) -> None:
        self._events.append(event)

    def pull_events(self) -> list[DomainEvent]:
        events, self._events = self._events, []
        return events

    def __eq__(self, other: object) -> bool:
        return isinstance(other, type(self)) and other.id == self.id

    def __hash__(self) -> int:
        return hash(self.id)
