"""Alembic environment. The connection comes from settings (DATABASE_URL), normalized the same way as the
app (Supabase/Neon strings work as pasted). DATABASE_SCHEMA, when set, scopes the migration to that schema
(integration tests use a throwaway schema per run)."""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import text
from sqlalchemy.engine import Connection

import hinglish.platform.tables  # noqa: F401  (registers tables on the metadata)
from hinglish.bootstrap.settings import Settings
from hinglish.platform.database import create_engine, metadata

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

target_metadata = metadata


def _settings() -> Settings:
    settings: Settings | None = config.attributes.get("settings")
    return settings or Settings()


def _url_and_schema() -> tuple[str, str | None]:
    s = _settings()
    if s.database_url is None:
        raise SystemExit("DATABASE_URL is not set; nothing to migrate.")
    return s.database_url.get_secret_value(), s.database_schema


def run_migrations_offline() -> None:
    url, schema = _url_and_schema()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table_schema=schema,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    _, schema = _url_and_schema()
    if schema:
        connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
        connection.commit()
    context.configure(connection=connection, target_metadata=target_metadata, version_table_schema=schema)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    url, schema = _url_and_schema()
    engine = create_engine(url, search_path=schema)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
