"""LanguageTagger: per-word hi/en/other tags without any model (FR-4.1 fallback).

Rules, in order: any Devanagari letter → hi; a Romanized-Hindi lexicon match → hi; contains a Latin
letter → en; anything else (numbers, symbols) → other. Punctuation is stripped before matching but the
original token is kept as the word.
"""

from __future__ import annotations

import re

from hinglish.linguistics.domain.lexicon import ROMAN_HINDI
from hinglish.shared_kernel.language import LanguageTag, TaggedWord, TaggedWords

_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_LATIN = re.compile(r"[A-Za-z]")
_EDGE_PUNCT = re.compile(r"^[^\wऀ-ॿ]+|[^\wऀ-ॿ]+$")
_DANDA = "।॥"  # । ॥ (sentence marks; never part of a word)


class LanguageTagger:
    def __init__(self, lexicon: frozenset[str] = ROMAN_HINDI) -> None:
        self._lexicon = lexicon

    def tag(self, text: str) -> TaggedWords:
        items: list[TaggedWord] = []
        for raw in text.split():
            word = _EDGE_PUNCT.sub("", raw.strip(_DANDA))
            if not word:
                continue
            items.append(TaggedWord(word, self.classify(word)))
        return TaggedWords(tuple(items))

    def classify(self, word: str) -> LanguageTag:
        if _DEVANAGARI.search(word):
            return "hi"
        if word.lower() in self._lexicon:
            return "hi"
        if _LATIN.search(word):
            return "en"
        return "other"
