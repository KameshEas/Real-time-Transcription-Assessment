"""Initial schema: transcripts, segments, live_sessions, outbox_events, usage_records, idempotency_keys.

Revision ID: 0001
Revises:
Create Date: 2026-11-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = pg.UUID(as_uuid=True)
TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "transcripts",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.Text, nullable=False, server_default="public"),
        sa.Column("owner_id", sa.Text),
        sa.Column("title", sa.String(200), nullable=False, server_default="Untitled"),
        sa.Column("engine", sa.String(20), nullable=False),
        sa.Column("model_id", sa.String(80)),
        sa.Column("script_mode", sa.String(20), nullable=False, server_default="mixed"),
        sa.Column("full_text", sa.Text, nullable=False, server_default=""),
        sa.Column("hindi_ratio", sa.Numeric(4, 3)),
        sa.Column("edited", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("duration_ms", sa.Integer),
        sa.Column("segment_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="recording"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column(
            "search_tsv",
            pg.TSVECTOR,
            sa.Computed("to_tsvector('simple'::regconfig, title || ' ' || full_text)", persisted=True),
        ),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", TS),
        sa.CheckConstraint("engine IN ('sarvam', 'manual', 'fake')", name="ck_transcripts_engine"),
        sa.CheckConstraint("status IN ('recording', 'completed')", name="ck_transcripts_status"),
        sa.CheckConstraint(
            "script_mode IN ('mixed', 'devanagari', 'roman')", name="ck_transcripts_script_mode"
        ),
        sa.CheckConstraint("hindi_ratio IS NULL OR hindi_ratio BETWEEN 0 AND 1", name="ck_transcripts_ratio"),
    )
    # Cursor pagination over live rows (tenant, not deleted), newest first.
    op.create_index(
        "ix_transcripts_tenant_created",
        "transcripts",
        ["tenant_id", sa.text("created_at DESC"), sa.text("id DESC")],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    # 'simple' config: Hindi and Hinglish words are not stemmed with English rules.
    op.create_index("ix_transcripts_search", "transcripts", ["search_tsv"], postgresql_using="gin")

    op.create_table(
        "segments",
        sa.Column("transcript_id", UUID, sa.ForeignKey("transcripts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("seq", sa.Integer, nullable=False),
        sa.Column("start_ms", sa.Integer),
        sa.Column("end_ms", sa.Integer),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("text_deva", sa.Text),
        sa.Column("text_roman", sa.Text),
        sa.Column("language", sa.String(16)),
        sa.Column("words", pg.JSONB),  # {"v": 1, "items": [{"w": "meeting", "lang": "en"}]}
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("transcript_id", "seq", name="pk_segments"),
        sa.CheckConstraint("seq > 0", name="ck_segments_seq_positive"),
    )

    op.create_table(
        "live_sessions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("transcript_id", UUID, sa.ForeignKey("transcripts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("engine", sa.String(20), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("started_at", TS, nullable=False),
        sa.Column("ended_at", TS),
        sa.Column("close_reason", sa.String(40)),
        sa.Column("first_partial_ms", sa.Integer),
        sa.Column("segments", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index("ix_live_sessions_transcript", "live_sessions", ["transcript_id"])

    op.create_table(
        "outbox_events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("aggregate_id", UUID, nullable=False),
        sa.Column("type", sa.String(60), nullable=False),
        sa.Column("payload", pg.JSONB, nullable=False),
        sa.Column("occurred_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("published_at", TS),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_outbox_unpublished", "outbox_events", ["id"], postgresql_where=sa.text("published_at IS NULL")
    )

    op.create_table(
        "usage_records",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Text, nullable=False, server_default="public"),
        sa.Column("vendor", sa.String(20), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),  # stt_seconds | tts_chars | llm_tokens
        sa.Column("quantity", sa.Numeric(12, 2), nullable=False),
        sa.Column("session_id", UUID),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "idempotency_keys",
        sa.Column("key", sa.Text, primary_key=True),
        sa.Column("tenant_id", sa.Text, nullable=False, server_default="public"),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("status_code", sa.Integer, nullable=False),
        sa.Column("response", pg.JSONB, nullable=False),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    for table in (
        "idempotency_keys",
        "usage_records",
        "outbox_events",
        "live_sessions",
        "segments",
        "transcripts",
    ):
        op.drop_table(table)
