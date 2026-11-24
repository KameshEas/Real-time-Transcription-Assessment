"""The adapter's translation of Sarvam realtime messages (shapes match the spike's real sessions)."""

from sarvamai.types.realtime_error import RealtimeError
from sarvamai.types.realtime_session_begin import RealtimeSessionBegin
from sarvamai.types.realtime_transcript_final import RealtimeTranscriptFinal
from sarvamai.types.realtime_transcript_partial import RealtimeTranscriptPartial

from hinglish.transcription.infrastructure.sarvam_realtime import SCRIPT_TO_MODE, _map_message


def test_script_modes() -> None:
    assert SCRIPT_TO_MODE == {"mixed": "codemix", "roman": "translit", "devanagari": "transcribe"}


def test_partial_and_final() -> None:
    p = _map_message(RealtimeTranscriptPartial(utterance_idx=0, text="aaj ki", language="hi-IN"))
    assert p is not None
    assert (p.kind, p.text, p.utterance, p.language) == ("partial", "aaj ki", 0, "hi-IN")
    text = "आज की meeting में हम budget discuss करेंगे।"
    f = _map_message(RealtimeTranscriptFinal(utterance_idx=2, text=text))
    assert f is not None
    assert (f.kind, f.text, f.utterance) == ("final", text, 2)


def test_auth_error_is_fatal_and_not_retryable() -> None:
    e = _map_message(
        RealtimeError(code="invalid_subscription_key", is_fatal=True, message="bad key", status_code=401)
    )
    assert e is not None
    assert (e.kind, e.error_code, e.fatal, e.retryable) == ("error", "ENGINE_AUTH", True, False)


def test_unknown_error_maps_to_engine_error() -> None:
    e = _map_message(RealtimeError(code="something_new", is_fatal=False, message="?"))
    assert e is not None
    assert (e.error_code, e.fatal, e.retryable) == ("ENGINE_ERROR", False, True)


def test_control_messages_are_ignored() -> None:
    assert _map_message(RealtimeSessionBegin(request_id="r1")) is None
