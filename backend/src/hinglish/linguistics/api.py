"""Public facade of the Linguistics context. Other contexts import only this module."""

from __future__ import annotations

from hinglish.linguistics.domain.tagger import LanguageTagger
from hinglish.shared_kernel.language import TaggedWords

_tagger = LanguageTagger()


def tag_words(text: str) -> TaggedWords:
    """Per-word hi/en/other tags for one segment of text."""
    return _tagger.tag(text)


__all__ = ["LanguageTagger", "tag_words"]
