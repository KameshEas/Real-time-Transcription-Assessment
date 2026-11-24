from hinglish.transcription.application.ports.speech_recognizer import RecognizerConfig
from hinglish.transcription.infrastructure.fake_recognizer import FakeRecognizer


async def test_fake_recognizer_emits_partials_then_final():
    session = await FakeRecognizer().open(RecognizerConfig())
    for _ in range(15):
        await session.send_audio(b"\x00" * 3200)
    await session.close()
    kinds = [e.kind async for e in session.events()]
    assert kinds == ["partial", "partial", "final"]
