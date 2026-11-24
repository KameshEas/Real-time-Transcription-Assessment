"""Composition root: the only module that knows concrete adapters. Wires ports by settings."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncEngine

from hinglish.bootstrap.settings import Settings
from hinglish.linguistics.api import tag_words
from hinglish.platform.database import create_engine, session_factory
from hinglish.platform.idempotency import IdempotencyStore, MemoryIdempotencyStore, SqlIdempotencyStore
from hinglish.shared_kernel import Clock, SystemClock
from hinglish.transcription.application.live_transcription import LiveTranscription
from hinglish.transcription.application.ports.live_sessions import LiveSessionRepository
from hinglish.transcription.application.ports.speech_recognizer import SpeechRecognizer
from hinglish.transcription.domain.session_policy import SessionPolicy
from hinglish.transcription.infrastructure.fake_recognizer import FakeRecognizer
from hinglish.transcription.infrastructure.live_sessions import (
    MemoryLiveSessionRepository,
    SqlLiveSessionRepository,
)
from hinglish.transcription.infrastructure.sarvam_realtime import SarvamRealtimeRecognizer
from hinglish.transcripts.api import TranscriptsModule, build_transcripts_module
from hinglish.transcripts.infrastructure.memory import (
    MemoryStore,
    MemoryTranscriptReadModel,
    MemoryUnitOfWork,
)
from hinglish.transcripts.infrastructure.sql import SqlTranscriptReadModel, SqlUnitOfWork, ping


class ConfigurationError(RuntimeError):
    pass


@dataclass
class Container:
    settings: Settings
    clock: Clock
    session_policy: SessionPolicy
    transcripts: TranscriptsModule
    live_transcription: LiveTranscription
    idempotency: IdempotencyStore
    recognizers: dict[str, SpeechRecognizer] = field(default_factory=dict)
    engine: AsyncEngine | None = None
    db_ping: Callable[[], Awaitable[None]] | None = None

    async def aclose(self) -> None:
        if self.engine is not None:
            await self.engine.dispose()


def build_recognizers(settings: Settings) -> dict[str, SpeechRecognizer]:
    """Engines a client may pick in `start.engine`. The fake engine is never offered in production."""
    recognizers: dict[str, SpeechRecognizer] = {}
    if settings.enable_sarvam and settings.sarvam_api_key is not None:
        recognizers["sarvam"] = SarvamRealtimeRecognizer(
            settings.sarvam_api_key.get_secret_value(),
            model=settings.sarvam_stt_model,
            stream_type=settings.sarvam_stream_type,
        )
    if settings.use_fake_recognizer or settings.app_env != "production":
        recognizers["fake"] = FakeRecognizer()
    return recognizers


def build_container(settings: Settings) -> Container:
    clock = SystemClock()
    engine: AsyncEngine | None = None
    db_ping = None
    live_sessions: LiveSessionRepository
    idempotency: IdempotencyStore

    if settings.persistence_backend == "postgres":
        if settings.database_url is None:
            raise ConfigurationError(
                "DATABASE_URL is not set. Add it to .env, "
                "or set PERSISTENCE_BACKEND=memory to run without a database."
            )
        engine = create_engine(settings.database_url.get_secret_value(), search_path=settings.database_schema)
        sessions = session_factory(engine)
        transcripts = build_transcripts_module(
            uow=lambda: SqlUnitOfWork(sessions),
            read_model=SqlTranscriptReadModel(sessions),
            clock=clock,
            tag=tag_words,
        )
        live_sessions = SqlLiveSessionRepository(sessions)
        idempotency = SqlIdempotencyStore(sessions)

        async def _ping() -> None:
            await ping(sessions)

        db_ping = _ping
    else:
        store = MemoryStore()
        transcripts = build_transcripts_module(
            uow=lambda: MemoryUnitOfWork(store),
            read_model=MemoryTranscriptReadModel(store),
            clock=clock,
            tag=tag_words,
        )
        live_sessions = MemoryLiveSessionRepository()
        idempotency = MemoryIdempotencyStore()

    return Container(
        settings=settings,
        clock=clock,
        session_policy=SessionPolicy(max_duration_s=float(settings.max_session_seconds)),
        transcripts=transcripts,
        live_transcription=LiveTranscription(transcripts, live_sessions, clock),
        idempotency=idempotency,
        recognizers=build_recognizers(settings),
        engine=engine,
        db_ping=db_ping,
    )
