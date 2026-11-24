from hinglish.transcription.application.ports.speech_recognizer import RecognizerConfig
from hinglish.transcription.infrastructure.fake_recognizer import FakeRecognizer

FRAME = b"\x00" * 3200


async def collect(frames: int) -> list[tuple[str, str, int]]:
    session = await FakeRecognizer().open(RecognizerConfig())
    for _ in range(frames):
        await session.send_audio(FRAME)
    await session.close()
    return [(e.kind, e.text, e.utterance) async for e in session.events()]


async def test_partials_grow_then_final():
    assert await collect(15) == [
        ("partial", "aaj ki meeting", 0),
        ("partial", "aaj ki meeting mein hum budget", 0),
        ("final", "aaj ki meeting mein hum budget discuss karenge", 0),
    ]


async def test_close_finalizes_pending_utterance():
    events = await collect(20)
    assert events[-1] == ("final", "aaj ki meeting", 1)


async def test_no_events_after_close():
    session = await FakeRecognizer().open(RecognizerConfig())
    await session.close()
    for _ in range(10):
        await session.send_audio(FRAME)
    assert [e async for e in session.events()] == []
