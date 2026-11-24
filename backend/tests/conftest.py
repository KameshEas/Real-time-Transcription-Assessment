"""Test fixtures.

`client` runs every API/gateway test against the in-memory backend and, when TEST_DATABASE_URL is set,
again against real PostgreSQL. Postgres tests run in a throwaway schema created by the real Alembic
migration and dropped at the end, so they never touch existing tables (safe on a shared Supabase DB).
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import text

from hinglish.bootstrap.app import create_app
from hinglish.bootstrap.settings import Settings
from hinglish.platform.database import create_engine

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
BACKENDS = ["memory", *(["postgres"] if TEST_DATABASE_URL else [])]
TABLES = "transcripts, segments, live_sessions, outbox_events, usage_records, idempotency_keys"


def _base(**overrides: object) -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        app_env="test",
        use_fake_recognizer=True,
        sarvam_api_key=None,
        groq_api_key=None,
        **overrides,  # type: ignore[arg-type]
    )


async def _execute(sql: str, schema: str | None = None) -> None:
    assert TEST_DATABASE_URL
    engine = create_engine(TEST_DATABASE_URL, search_path=schema)
    try:
        async with engine.begin() as conn:
            await conn.execute(text(sql))
    finally:
        await engine.dispose()


@pytest.fixture(scope="session")
def pg_settings() -> Iterator[Settings]:
    """Migrated throwaway schema for the whole session."""
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL not set")
    from alembic import command
    from alembic.config import Config

    schema = f"test_{uuid4().hex[:12]}"
    settings = _base(
        persistence_backend="postgres", database_url=SecretStr(TEST_DATABASE_URL), database_schema=schema
    )
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.attributes["settings"] = settings
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")
    try:
        yield settings
    finally:
        asyncio.run(_execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))


@pytest.fixture(params=BACKENDS)
def settings(request: pytest.FixtureRequest) -> Settings:
    if request.param == "memory":
        return _base(persistence_backend="memory")
    pg: Settings = request.getfixturevalue("pg_settings")
    asyncio.run(_execute(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE", pg.database_schema))
    return pg


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as c:
        yield c
