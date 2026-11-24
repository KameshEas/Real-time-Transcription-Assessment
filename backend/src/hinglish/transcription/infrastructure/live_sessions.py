from __future__ import annotations

import copy
from typing import Any
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hinglish.platform.tables import live_sessions
from hinglish.transcription.domain.live_session import LiveSession


def _row(s: LiveSession) -> dict[str, Any]:
    return {
        "id": s.id,
        "transcript_id": s.transcript_id,
        "engine": s.engine,
        "state": s.state.value,
        "started_at": s.started_at,
        "ended_at": s.ended_at,
        "close_reason": s.close_reason,
        "first_partial_ms": s.first_partial_ms,
        "segments": s.segments,
    }


class SqlLiveSessionRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def save(self, session: LiveSession) -> None:
        row = _row(session)
        stmt = pg_insert(live_sessions).values(row)
        stmt = stmt.on_conflict_do_update(
            index_elements=[live_sessions.c.id],
            set_={k: stmt.excluded[k] for k in row if k not in ("id", "transcript_id", "started_at")},
        )
        async with self._sessions() as db, db.begin():
            await db.execute(stmt)


class MemoryLiveSessionRepository:
    def __init__(self) -> None:
        self.rows: dict[UUID, LiveSession] = {}

    async def save(self, session: LiveSession) -> None:
        self.rows[session.id] = copy.deepcopy(session)
