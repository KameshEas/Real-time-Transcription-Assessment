"""Transactional outbox: domain events are inserted in the same transaction as the state change.
The relay (worker, Day 3) publishes them; handlers are idempotent (at-least-once delivery)."""

from __future__ import annotations

import dataclasses
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from hinglish.platform.tables import outbox_events
from hinglish.shared_kernel import DomainEvent


def _json_safe(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def event_record(event: DomainEvent) -> dict[str, Any]:
    payload = {
        k: _json_safe(v)
        for k, v in dataclasses.asdict(event).items()
        if k not in ("aggregate_id", "occurred_at")
    }
    return {
        "aggregate_id": event.aggregate_id,
        "type": event.type,
        "payload": payload,
        "occurred_at": event.occurred_at,
    }


async def write_outbox(session: AsyncSession, events: list[DomainEvent]) -> None:
    if events:
        await session.execute(insert(outbox_events), [event_record(e) for e in events])
