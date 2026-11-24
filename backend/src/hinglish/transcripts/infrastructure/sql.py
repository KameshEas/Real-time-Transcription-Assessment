"""PostgreSQL adapters: repository + unit of work (write side) and read model (query side)."""

from __future__ import annotations

from types import TracebackType
from typing import Any, Self
from uuid import UUID

from sqlalchemy import delete, func, insert, or_, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hinglish.messaging.outbox import write_outbox
from hinglish.platform.tables import segments, transcripts
from hinglish.shared_kernel import DomainEvent, TenantId
from hinglish.transcripts.application.cursor import decode_cursor, encode_cursor
from hinglish.transcripts.application.dto import Page, SearchQuery, TranscriptDetail, TranscriptSummary
from hinglish.transcripts.domain.errors import VersionConflict
from hinglish.transcripts.domain.transcript import Transcript
from hinglish.transcripts.infrastructure.mapping import segment_row, to_aggregate, transcript_row

CONFLICT_MSG = "This transcript was changed by someone else. Reload and try again."


async def _load(
    session: AsyncSession, tenant_id: TenantId, id: UUID, include_deleted: bool
) -> Transcript | None:
    cond = [transcripts.c.id == id, transcripts.c.tenant_id == tenant_id]
    if not include_deleted:
        cond.append(transcripts.c.deleted_at.is_(None))
    row = (await session.execute(select(transcripts).where(*cond))).mappings().first()
    if row is None:
        return None
    seg_rows = (
        (
            await session.execute(
                select(segments).where(segments.c.transcript_id == id).order_by(segments.c.seq)
            )
        )
        .mappings()
        .all()
    )
    return to_aggregate(row, seg_rows)


class SqlTranscriptRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._tracked: dict[UUID, tuple[Transcript, int | None]] = {}  # aggregate, version when loaded
        self._removed: dict[UUID, tuple[Transcript, int]] = {}

    async def get(self, tenant_id: TenantId, id: UUID, *, include_deleted: bool = False) -> Transcript | None:
        t = await _load(self._session, tenant_id, id, include_deleted)
        if t is not None:
            self._tracked[t.id] = (t, t.version)
        return t

    def add(self, transcript: Transcript) -> None:
        self._tracked[transcript.id] = (transcript, None)

    def remove(self, transcript: Transcript) -> None:
        _, loaded = self._tracked.pop(transcript.id, (transcript, transcript.version))
        self._removed[transcript.id] = (transcript, loaded or transcript.version)

    async def flush(self) -> list[DomainEvent]:
        events: list[DomainEvent] = []
        for t, loaded_version in self._tracked.values():
            events += t.pull_events()
            if loaded_version is None:
                await self._session.execute(insert(transcripts).values(transcript_row(t)))
            elif t.version != loaded_version:
                row = transcript_row(t)
                del row["id"], row["created_at"]
                result = await self._session.execute(
                    update(transcripts)
                    .where(transcripts.c.id == t.id, transcripts.c.version == loaded_version)
                    .values(row)
                )
                if result.rowcount == 0:  # type: ignore[attr-defined]
                    raise VersionConflict(CONFLICT_MSG)
            dirty = t.pull_dirty_segments()
            if dirty:
                stmt = pg_insert(segments).values([segment_row(t.id, seg) for seg in dirty])
                stmt = stmt.on_conflict_do_update(
                    index_elements=[segments.c.transcript_id, segments.c.seq],
                    set_={
                        c: stmt.excluded[c] for c in ("text", "text_deva", "text_roman", "words", "language")
                    },
                )
                await self._session.execute(stmt)
        for t, loaded_version in self._removed.values():
            events += t.pull_events()
            result = await self._session.execute(
                delete(transcripts).where(transcripts.c.id == t.id, transcripts.c.version == loaded_version)
            )
            if result.rowcount == 0:  # type: ignore[attr-defined]
                raise VersionConflict(CONFLICT_MSG)
        return events


class SqlUnitOfWork:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def __aenter__(self) -> Self:
        self._session = self._sessions()
        self.transcripts = SqlTranscriptRepository(self._session)
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        try:
            if self._session.in_transaction():
                await self._session.rollback()
        finally:
            await self._session.close()

    async def commit(self) -> None:
        events = await self.transcripts.flush()
        await write_outbox(self._session, events)
        await self._session.commit()


def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


SUMMARY_COLUMNS = (
    transcripts.c.id,
    transcripts.c.title,
    transcripts.c.engine,
    transcripts.c.script_mode,
    transcripts.c.status,
    transcripts.c.hindi_ratio,
    transcripts.c.edited,
    transcripts.c.duration_ms,
    transcripts.c.segment_count,
    func.left(transcripts.c.full_text, 200).label("preview"),
    transcripts.c.version,
    transcripts.c.created_at,
    transcripts.c.updated_at,
)


def _summary(r: Any) -> TranscriptSummary:
    return TranscriptSummary(
        id=r.id,
        title=r.title,
        engine=r.engine,
        script_mode=r.script_mode,
        status=r.status,
        hindi_ratio=float(r.hindi_ratio) if r.hindi_ratio is not None else None,
        edited=r.edited,
        duration_ms=r.duration_ms,
        segment_count=r.segment_count,
        preview=r.preview,
        version=r.version,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


class SqlTranscriptReadModel:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def search(self, tenant_id: TenantId, query: SearchQuery) -> Page:
        stmt = select(*SUMMARY_COLUMNS).where(
            transcripts.c.tenant_id == tenant_id, transcripts.c.deleted_at.is_(None)
        )
        if query.q and query.q.strip():
            q = query.q.strip()
            stmt = stmt.where(
                or_(
                    transcripts.c.search_tsv.op("@@")(func.websearch_to_tsquery("simple", q)),
                    transcripts.c.title.ilike(f"%{_escape_like(q)}%", escape="\\"),
                )
            )
        if query.engine:
            stmt = stmt.where(transcripts.c.engine == query.engine)
        if query.created_from:
            stmt = stmt.where(transcripts.c.created_at >= query.created_from)
        if query.created_to:
            stmt = stmt.where(transcripts.c.created_at < query.created_to)
        if query.cursor:
            c_at, c_id = decode_cursor(query.cursor)
            stmt = stmt.where(tuple_(transcripts.c.created_at, transcripts.c.id) < tuple_(c_at, c_id))
        stmt = stmt.order_by(transcripts.c.created_at.desc(), transcripts.c.id.desc()).limit(query.limit + 1)

        async with self._sessions() as session:
            rows = (await session.execute(stmt)).all()
        items = [_summary(r) for r in rows[: query.limit]]
        next_cursor = (
            encode_cursor(items[-1].created_at, items[-1].id) if len(rows) > query.limit and items else None
        )
        return Page(items=tuple(items), next_cursor=next_cursor)

    async def get(self, tenant_id: TenantId, id: UUID) -> TranscriptDetail | None:
        async with self._sessions() as session:
            t = await _load(session, tenant_id, id, include_deleted=False)
        return TranscriptDetail.of(t) if t else None


async def ping(sessions: async_sessionmaker[AsyncSession]) -> None:
    async with sessions() as session:
        await session.execute(select(1))


__all__ = ["SqlTranscriptReadModel", "SqlTranscriptRepository", "SqlUnitOfWork", "ping"]
