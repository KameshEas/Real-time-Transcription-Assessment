import time

from hinglish.shared_kernel.ids import new_id


def test_uuid7_layout():
    u = new_id()
    assert u.version == 7
    assert (u.int >> 62) & 0b11 == 0b10  # RFC 9562 variant
    assert abs((u.int >> 80) - time.time_ns() // 1_000_000) < 5_000  # embedded ms timestamp


def test_ids_are_strictly_increasing_even_within_one_millisecond():
    ids = [new_id() for _ in range(10_000)]
    assert ids == sorted(ids) and len(set(ids)) == len(ids)
