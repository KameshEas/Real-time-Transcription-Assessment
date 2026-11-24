"""Bounded downlink buffer with the backpressure rule from ARCHITECTURE §10:
when full, stale partials are dropped; finals and control messages are never dropped."""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Outbound:
    payload: dict[str, Any]
    droppable: bool = False  # True only for partials


class OutboundBuffer:
    def __init__(self, capacity: int = 64) -> None:
        self._items: deque[Outbound] = deque()
        self._capacity = capacity
        self._ready = asyncio.Event()
        self._closed = False
        self.dropped = 0

    def put(self, item: Outbound) -> None:
        if self._closed:
            return
        full = len(self._items) >= self._capacity
        if full and not self._evict_one_partial() and item.droppable:
            self.dropped += 1
            return
        # When the buffer holds only finals/control messages, a new one overshoots capacity rather
        # than being dropped: finals are never lost.
        self._items.append(item)
        self._ready.set()

    def close(self) -> None:
        """No more items; `get` drains what is left, then returns None."""
        self._closed = True
        self._ready.set()

    async def get(self) -> Outbound | None:
        while not self._items:
            if self._closed:
                return None
            self._ready.clear()
            await self._ready.wait()
        return self._items.popleft()

    def __len__(self) -> int:
        return len(self._items)

    def _evict_one_partial(self) -> bool:
        for i, queued in enumerate(self._items):
            if queued.droppable:
                del self._items[i]
                self.dropped += 1
                return True
        return False
