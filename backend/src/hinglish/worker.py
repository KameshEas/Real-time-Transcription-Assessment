"""Worker entrypoint: `python -m hinglish.worker`. Runs the outbox relay and job handlers."""

from __future__ import annotations

import asyncio

import structlog

from hinglish.bootstrap.settings import get_settings
from hinglish.observability.logging import configure_logging

log = structlog.get_logger()


async def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    log.info("worker.started", queue_backend=settings.queue_backend)
    # TODO(Day 3): outbox relay -> JobQueue -> handlers.
    await asyncio.Event().wait()  # placeholder until the relay loop exists


if __name__ == "__main__":
    asyncio.run(run())
