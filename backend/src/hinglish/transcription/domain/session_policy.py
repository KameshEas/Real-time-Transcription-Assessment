"""Limits on a live session. Pure domain rules, standard library only."""

from __future__ import annotations

from dataclasses import dataclass

MAX_FRAME_BYTES = 16_000  # vendor per-frame cap; a 100 ms 16 kHz int16 frame is 3,200 bytes


@dataclass(frozen=True, slots=True)
class SessionPolicy:
    max_duration_s: float = 600.0
    idle_timeout_s: float = 60.0
    start_timeout_s: float = 10.0

    def exceeded(self, elapsed_s: float) -> bool:
        return elapsed_s >= self.max_duration_s

    @staticmethod
    def frame_is_valid(frame: bytes) -> bool:
        """Non-empty, whole 16-bit samples, under the vendor cap."""
        return 0 < len(frame) <= MAX_FRAME_BYTES and len(frame) % 2 == 0
