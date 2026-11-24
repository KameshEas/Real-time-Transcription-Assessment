"""All tables (ARCHITECTURE §11), registered on the shared metadata. Persistence models are separate from
domain classes; repositories map between them. The Alembic migration is the source of truth for DDL;
these definitions must match it (an integration test checks the migration builds these tables)."""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    String,
    Table,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID

from hinglish.platform.database import metadata

ENGINES = ("sarvam", "manual", "fake")

transcripts = Table(
    "transcripts",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
    Column("tenant_id", Text, nullable=False, server_default="public"),
    Column("owner_id", Text),
    Column("title", String(200), nullable=False, server_default="Untitled"),
    Column("engine", String(20), nullable=False),
    Column("model_id", String(80)),
    Column("script_mode", String(20), nullable=False, server_default="mixed"),
    Column("full_text", Text, nullable=False, server_default=""),
    Column("hindi_ratio", Numeric(4, 3)),
    Column("edited", Boolean, nullable=False, server_default=text("false")),
    Column("duration_ms", Integer),
    Column("segment_count", Integer, nullable=False, server_default="0"),
    Column("status", String(20), nullable=False, server_default="recording"),
    Column("version", Integer, nullable=False, server_default="1"),
    Column(
        "search_tsv",
        TSVECTOR,
        Computed("to_tsvector('simple'::regconfig, title || ' ' || full_text)", persisted=True),
    ),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("deleted_at", DateTime(timezone=True)),
    CheckConstraint(f"engine IN {ENGINES}", name="engine"),
    CheckConstraint("status IN ('recording', 'completed')", name="status"),
    CheckConstraint("script_mode IN ('mixed', 'devanagari', 'roman')", name="script_mode"),
)
Index(
    "ix_transcripts_tenant_created",
    transcripts.c.tenant_id,
    transcripts.c.created_at.desc(),
    transcripts.c.id.desc(),
    postgresql_where=transcripts.c.deleted_at.is_(None),
)
Index("ix_transcripts_search", transcripts.c.search_tsv, postgresql_using="gin")

segments = Table(
    "segments",
    metadata,
    Column(
        "transcript_id",
        UUID(as_uuid=True),
        ForeignKey("transcripts.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("seq", Integer, nullable=False),
    Column("start_ms", Integer),
    Column("end_ms", Integer),
    Column("text", Text, nullable=False),
    Column("text_deva", Text),
    Column("text_roman", Text),
    Column("language", String(16)),
    Column("words", JSONB),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    PrimaryKeyConstraint("transcript_id", "seq"),
)

live_sessions = Table(
    "live_sessions",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column(
        "transcript_id",
        UUID(as_uuid=True),
        ForeignKey("transcripts.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("engine", String(20), nullable=False),
    Column("state", String(20), nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("ended_at", DateTime(timezone=True)),
    Column("close_reason", String(40)),
    Column("first_partial_ms", Integer),
    Column("segments", Integer, nullable=False, server_default="0"),
)
Index("ix_live_sessions_transcript", live_sessions.c.transcript_id)

outbox_events = Table(
    "outbox_events",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("aggregate_id", UUID(as_uuid=True), nullable=False),
    Column("type", String(60), nullable=False),
    Column("payload", JSONB, nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("published_at", DateTime(timezone=True)),
    Column("attempts", Integer, nullable=False, server_default="0"),
)
Index("ix_outbox_unpublished", outbox_events.c.id, postgresql_where=outbox_events.c.published_at.is_(None))

usage_records = Table(
    "usage_records",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("tenant_id", Text, nullable=False, server_default="public"),
    Column("vendor", String(20), nullable=False),
    Column("kind", String(20), nullable=False),
    Column("quantity", Numeric(12, 2), nullable=False),
    Column("session_id", UUID(as_uuid=True)),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

idempotency_keys = Table(
    "idempotency_keys",
    metadata,
    Column("key", Text, primary_key=True),
    Column("tenant_id", Text, nullable=False, server_default="public"),
    Column("request_hash", String(64), nullable=False),
    Column("status_code", Integer, nullable=False),
    Column("response", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)
