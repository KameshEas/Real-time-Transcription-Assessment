"""Shared SQL infrastructure: engine/session factory and the metadata every context registers tables on.

Accepts connection strings as providers hand them out (Supabase, Neon, local):
- `postgres://` / `postgresql://` are switched to the asyncpg driver
- `sslmode=require|verify-*` becomes asyncpg's `ssl` argument (asyncpg ignores libpq's `sslmode`)
- remote hosts default to SSL; localhost does not
- PgBouncer transaction pooling (Supabase port 6543) can't keep prepared statements, so the statement
  cache is disabled and statement names are made unique per execution
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy import MetaData
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.ext.asyncio import AsyncSession as AsyncSession
from sqlalchemy.pool import NullPool

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
metadata = MetaData(naming_convention=NAMING)

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "postgres", "db"}
TRANSACTION_POOLER_PORT = 6543


def normalize_url(raw: str) -> tuple[URL, dict[str, Any], bool]:
    """Returns (asyncpg URL, connect_args, uses_transaction_pooler)."""
    url = make_url(raw.strip())
    if url.drivername in ("postgres", "postgresql", "postgresql+psycopg", "postgresql+psycopg2"):
        url = url.set(drivername="postgresql+asyncpg")
    query = dict(url.query)
    sslmode = query.pop("sslmode", None)
    query.pop("ssl", None)
    url = url.set(query=query)

    connect_args: dict[str, Any] = {}
    if isinstance(sslmode, str) and sslmode in ("require", "verify-ca", "verify-full"):
        connect_args["ssl"] = "require" if sslmode == "require" else True
    elif sslmode != "disable" and (url.host or "localhost") not in LOCAL_HOSTS:
        connect_args["ssl"] = "require"

    pooled = url.port == TRANSACTION_POOLER_PORT
    if pooled:
        connect_args["statement_cache_size"] = 0
        connect_args["prepared_statement_name_func"] = lambda: f"__asyncpg_{uuid4()}__"
    return url, connect_args, pooled


def create_engine(raw_url: str, *, search_path: str | None = None, echo: bool = False) -> AsyncEngine:
    url, connect_args, pooled = normalize_url(raw_url)
    if search_path:
        connect_args.setdefault("server_settings", {})["search_path"] = search_path
    kwargs: dict[str, Any] = {"echo": echo, "connect_args": connect_args}
    if pooled:
        kwargs["poolclass"] = NullPool  # the external pooler does the pooling
    else:
        kwargs.update(pool_size=5, max_overflow=5, pool_pre_ping=True, pool_recycle=1800)
    return create_async_engine(url, **kwargs)


def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
