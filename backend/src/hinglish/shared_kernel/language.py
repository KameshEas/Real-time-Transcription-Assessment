"""Per-word language tags, shared by Transcripts (storage) and Linguistics (tagging). Standard library only.

Wire/storage format (versioned, ADR-0006): {"v": 1, "items": [{"w": "meeting", "lang": "en"}, ...]}
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, cast

LanguageTag = Literal["hi", "en", "other"]
WORDS_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class TaggedWord:
    w: str
    lang: LanguageTag


@dataclass(frozen=True, slots=True)
class TaggedWords:
    items: tuple[TaggedWord, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"v": WORDS_SCHEMA_VERSION, "items": [{"w": t.w, "lang": t.lang} for t in self.items]}

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> TaggedWords:
        if not data:
            return cls()
        if data.get("v") != WORDS_SCHEMA_VERSION:
            raise ValueError(f"unsupported words schema version: {data.get('v')!r}")
        return cls(tuple(TaggedWord(i["w"], cast(LanguageTag, i["lang"])) for i in data["items"]))

    def counts(self) -> tuple[int, int]:
        """(hindi, english) word counts; 'other' (numbers, symbols) is ignored."""
        hi = sum(1 for t in self.items if t.lang == "hi")
        en = sum(1 for t in self.items if t.lang == "en")
        return hi, en


def hindi_ratio(words: list[TaggedWords] | tuple[TaggedWords, ...]) -> float | None:
    """Share of Hindi among Hindi+English words, rounded to 3 dp. None when there are no such words."""
    hi = en = 0
    for w in words:
        h, e = w.counts()
        hi += h
        en += e
    total = hi + en
    return round(hi / total, 3) if total else None
