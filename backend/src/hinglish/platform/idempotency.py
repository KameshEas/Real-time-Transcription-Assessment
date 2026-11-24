"""Idempotency-Key storage for POST retries: the first response is stored and replayed for the same key."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hinglish.platform.tables import idempotency_keys


@dataclass(frozen=True, slots=True)
class StoredResponse:
    request_hash: str
    status_code: int
    body: dict[str, Any]


class IdempotencyStore(Protocol):
    async def get(self, tenant_id: str, key: str) -> StoredResponse | None: ...

    async def put(self, tenant_id: str, key: str, response: StoredResponse) -> None: ...


class SqlIdempotencyStore:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def get(self, tenant_id: str, key: str) -> StoredResponse | None:
        async with self._sessions() as db:
            row = (
                (
                    await db.execute(
                        select(idempotency_keys).where(
                            idempotency_keys.c.key == key, idempotency_keys.c.tenant_id == tenant_id
                        )
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            return None
        return StoredResponse(row["request_hash"], row["status_code"], row["response"])

    async def put(self, tenant_id: str, key: str, response: StoredResponse) -> None:
        stmt = (
            pg_insert(idempotency_keys)
            .values(
                key=key,
                tenant_id=tenant_id,
                request_hash=response.request_hash,
                status_code=response.status_code,
                response=response.body,
            )
            .on_conflict_do_nothing(index_elements=[idempotency_keys.c.key])
        )
        async with self._sessions() as db, db.begin():
            await db.execute(stmt)


class MemoryIdempotencyStore:
    def __init__(self) -> None:
        self._data: dict[tuple[str, str], StoredResponse] = {}

    async def get(self, tenant_id: str, key: str) -> StoredResponse | None:
        return self._data.get((tenant_id, key))

    async def put(self, tenant_id: str, key: str, response: StoredResponse) -> None:
        self._data.setdefault((tenant_id, key), response)
