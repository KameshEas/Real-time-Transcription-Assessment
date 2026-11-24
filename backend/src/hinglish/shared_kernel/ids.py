from __future__ import annotations

import os
import threading
import time
from typing import NewType
from uuid import UUID

TenantId = NewType("TenantId", str)
PUBLIC_TENANT = TenantId("public")

_lock = threading.Lock()
_last_ms = 0
_counter = 0
_COUNTER_MAX = 0xFFF  # 12 bits (rand_a)


def new_id() -> UUID:
    """Monotonic UUIDv7 (RFC 9562): 48-bit Unix ms timestamp, then a 12-bit counter, then random bits.

    Ids sort in creation order even within one millisecond (Windows clocks tick coarsely), so
    `ORDER BY created_at DESC, id DESC` is a true newest-first order, and B-tree inserts stay local.
    Python 3.14 adds uuid.uuid7(); this keeps us on 3.12 with the same layout.
    """
    global _last_ms, _counter
    with _lock:
        ms = time.time_ns() // 1_000_000
        if ms > _last_ms:
            _last_ms = ms
            _counter = int.from_bytes(os.urandom(2)) & 0x7FF  # random start, room to count up
        else:
            _counter += 1
            if _counter > _COUNTER_MAX:  # >2k ids in one ms: borrow the next millisecond
                _last_ms += 1
                _counter = 0
        ms, counter = _last_ms, _counter
    rand_b = int.from_bytes(os.urandom(8)) & ((1 << 62) - 1)
    value = (ms << 80) | (0x7 << 76) | (counter << 64) | (0b10 << 62) | rand_b
    return UUID(int=value)
