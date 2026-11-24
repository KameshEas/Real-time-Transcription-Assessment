from typing import Any

from hinglish.transcription.application.outbound_buffer import Outbound, OutboundBuffer


def partial(n: int) -> Outbound:
    return Outbound({"type": "partial", "n": n}, droppable=True)


def final(n: int) -> Outbound:
    return Outbound({"type": "final", "n": n})


async def drain(buf: OutboundBuffer) -> list[dict[str, Any]]:
    buf.close()
    out = []
    while (item := await buf.get()) is not None:
        out.append(item.payload)
    return out


async def test_full_buffer_evicts_oldest_partial_for_newer_one():
    buf = OutboundBuffer(capacity=2)
    buf.put(partial(1))
    buf.put(partial(2))
    buf.put(partial(3))
    assert [m["n"] for m in await drain(buf)] == [2, 3]
    assert buf.dropped == 1


async def test_finals_are_never_dropped():
    buf = OutboundBuffer(capacity=2)
    buf.put(final(1))
    buf.put(final(2))
    buf.put(partial(3))  # nothing evictable: the partial is dropped
    buf.put(final(4))  # finals overshoot capacity rather than drop
    assert [m["n"] for m in await drain(buf)] == [1, 2, 4]
    assert buf.dropped == 1


async def test_partial_is_evicted_to_make_room_for_final():
    buf = OutboundBuffer(capacity=2)
    buf.put(partial(1))
    buf.put(final(2))
    buf.put(final(3))
    assert [m["n"] for m in await drain(buf)] == [2, 3]


async def test_put_after_close_is_ignored():
    buf = OutboundBuffer()
    buf.close()
    buf.put(final(1))
    assert await buf.get() is None
