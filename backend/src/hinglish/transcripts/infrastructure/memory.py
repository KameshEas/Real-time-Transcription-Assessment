"""In-memory adapters with the same semantics as the SQL ones (version checks, outbox, keyset paging).
Used by application tests and for running the app without a database (PERSISTENCE_BACKEND=memory)."""

from __future__ import annotations

import asyncio
import copy
from dataclasses import dataclass, field
from types import TracebackType
from typing import Self
from uuid import UUID

from hinglish.shared_kernel import DomainEvent, TenantId
from hinglish.transcripts.application.cursor import decode_cursor, encode_cursor
from hinglish.transcripts.application.dto import Page, SearchQuery, TranscriptDetail
from hinglish.transcripts.domain.errors import VersionConflict
from hinglish.transcripts.domain.transcript import Transcript, TranscriptState


@dataclass
class MemoryStore:
    rows: dict[UUID, TranscriptState] = field(default_factory=dict)
    outbox: list[DomainEvent] = field(default_factory=list)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def load(self, tenant_id: TenantId, id: UUID, include_deleted: bool) -> Transcript | None:
        state = self.rows.get(id)
        if state is None or state.tenant_id != tenant_id:
            return None
        if state.deleted_at is not None and not include_deleted:
            return None
        return Transcript(copy.deepcopy(state))


class MemoryTranscriptRepository:
    def __init__(self, store: MemoryStore) -> None:
        self._store = store
        self.tracked: dict[UUID, tuple[Transcript, int | None]] = {}
        self.removed: dict[UUID, tuple[Transcript, int]] = {}

    async def get(self, tenant_id: TenantId, id: UUID, *, include_deleted: bool = False) -> Transcript | None:
        t = self._store.load(tenant_id, id, include_deleted)
        if t is not None:
            self.tracked[t.id] = (t, t.version)
        return t

    def add(self, transcript: Transcript) -> None:
        self.tracked[transcript.id] = (transcript, None)

    def remove(self, transcript: Transcript) -> None:
        _, loaded = self.tracked.pop(transcript.id, (transcript, transcript.version))
        self.removed[transcript.id] = (transcript, loaded or transcript.version)


class MemoryUnitOfWork:
    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    async def __aenter__(self) -> Self:
        self.transcripts = MemoryTranscriptRepository(self._store)
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        return None

    async def commit(self) -> None:
        async with self._store.lock:
            repo = self.transcripts
            # Like SQL, only new or changed aggregates are written (and version-checked).
            changed = [(t, v) for t, v in repo.tracked.values() if v is None or t.version != v]
            # Check every version first so a failed commit changes nothing (like a rolled-back transaction).
            for t, loaded in [*changed, *repo.removed.values()]:
                current = self._store.rows.get(t.id)
                if loaded is not None and (current is None or current.version != loaded):
                    raise VersionConflict(
                        "This transcript was changed by someone else. Reload and try again."
                    )
            for t, _ in changed:
                self._store.outbox += t.pull_events()
                t.pull_dirty_segments()
                self._store.rows[t.id] = copy.deepcopy(t.state)
            for t, _ in repo.removed.values():
                self._store.outbox += t.pull_events()
                self._store.rows.pop(t.id, None)


class MemoryTranscriptReadModel:
    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    async def search(self, tenant_id: TenantId, query: SearchQuery) -> Page:
        found: list[Transcript] = []
        for state in self._store.rows.values():
            if state.tenant_id != tenant_id or state.deleted_at is not None:
                continue
            t = Transcript(copy.deepcopy(state))
            if query.q and query.q.strip().lower() not in f"{state.title}\n{t.full_text}".lower():
                continue
            if query.engine and state.engine.value != query.engine:
                continue
            if query.created_from and state.created_at < query.created_from:
                continue
            if query.created_to and state.created_at >= query.created_to:
                continue
            found.append(t)
        found.sort(key=lambda t: (t.state.created_at, t.id), reverse=True)
        if query.cursor:
            c_at, c_id = decode_cursor(query.cursor)
            found = [t for t in found if (t.state.created_at, t.id) < (c_at, c_id)]
        page = found[: query.limit]
        items = tuple(TranscriptDetail.of(t).summary for t in page)
        has_more = len(found) > query.limit
        next_cursor = encode_cursor(items[-1].created_at, items[-1].id) if has_more and items else None
        return Page(items=items, next_cursor=next_cursor)

    async def get(self, tenant_id: TenantId, id: UUID) -> TranscriptDetail | None:
        t = self._store.load(tenant_id, id, include_deleted=False)
        return TranscriptDetail.of(t) if t else None
