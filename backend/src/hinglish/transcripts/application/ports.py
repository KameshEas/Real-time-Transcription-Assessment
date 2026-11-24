"""Ports of the Transcripts context. Implemented in infrastructure (SQL and in-memory)."""

from __future__ import annotations

from collections.abc import Callable
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from hinglish.shared_kernel import TenantId
from hinglish.shared_kernel.language import TaggedWords
from hinglish.transcripts.application.dto import Page, SearchQuery, TranscriptDetail
from hinglish.transcripts.domain.transcript import Transcript

Tagger = Callable[[str], TaggedWords]


class TranscriptRepository(Protocol):
    async def get(self, tenant_id: TenantId, id: UUID, *, include_deleted: bool = False) -> Transcript | None:
        """Load the aggregate. Deleted transcripts are hidden unless asked for."""
        ...

    def add(self, transcript: Transcript) -> None: ...

    def remove(self, transcript: Transcript) -> None:
        """Hard delete on commit (segments cascade)."""
        ...


class UnitOfWork(Protocol):
    """One transaction. On commit, changed aggregates are written and their domain events go to the
    outbox in the same transaction. Raises VersionConflict if a row changed since it was loaded."""

    @property
    def transcripts(self) -> TranscriptRepository: ...

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None: ...

    async def commit(self) -> None: ...


UnitOfWorkFactory = Callable[[], UnitOfWork]


class TranscriptReadModel(Protocol):
    async def search(self, tenant_id: TenantId, query: SearchQuery) -> Page: ...

    async def get(self, tenant_id: TenantId, id: UUID) -> TranscriptDetail | None: ...
