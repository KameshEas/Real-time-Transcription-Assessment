import pytest

from hinglish.linguistics.domain.tagger import LanguageTagger
from hinglish.shared_kernel.language import TaggedWord, TaggedWords, hindi_ratio

tagger = LanguageTagger()


def tags(text: str) -> list[tuple[str, str]]:
    return [(t.w, t.lang) for t in tagger.tag(text).items]


def test_codemix_devanagari_with_english_words():
    assert tags("आज की meeting में budget discuss करेंगे।") == [
        ("आज", "hi"),
        ("की", "hi"),
        ("meeting", "en"),
        ("में", "hi"),
        ("budget", "en"),
        ("discuss", "en"),
        ("करेंगे", "hi"),
    ]


def test_romanized_hindi_uses_lexicon():
    assert tags("Aaj ki meeting mein budget discuss karenge.") == [
        ("Aaj", "hi"),
        ("ki", "hi"),
        ("meeting", "en"),
        ("mein", "hi"),
        ("budget", "en"),
        ("discuss", "en"),
        ("karenge", "hi"),
    ]


@pytest.mark.parametrize("word", ["to", "me", "the", "log", "mere", "use", "tab", "hi", "pure", "mile"])
def test_english_false_friends_stay_english(word: str):
    assert tagger.classify(word) == "en"


def test_numbers_and_symbols_are_other():
    assert tags("Friday 5 baje, 100% sure") == [
        ("Friday", "en"),
        ("5", "other"),
        ("baje", "en"),  # not in the lexicon: misses are acceptable, false hits are not
        ("100", "other"),
        ("sure", "en"),
    ]


def test_punctuation_only_tokens_are_dropped():
    assert tags("— । , ok") == [("ok", "en")]


def test_hindi_ratio_ignores_other_and_handles_empty():
    words = TaggedWords((TaggedWord("aaj", "hi"), TaggedWord("meeting", "en"), TaggedWord("5", "other")))
    assert hindi_ratio([words]) == 0.5
    assert hindi_ratio([TaggedWords()]) is None


def test_words_roundtrip_and_version_check():
    words = tagger.tag("aaj meeting")
    assert TaggedWords.from_dict(words.to_dict()) == words
    assert words.to_dict()["v"] == 1
    with pytest.raises(ValueError):
        TaggedWords.from_dict({"v": 2, "items": []})
