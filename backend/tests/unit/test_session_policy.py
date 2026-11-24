import pytest

from hinglish.transcription.domain.session_policy import SessionPolicy


@pytest.mark.parametrize(
    ("frame", "valid"),
    [
        (b"", False),
        (b"\x00", False),
        (b"\x00" * 3200, True),
        (b"\x00" * 16_000, True),
        (b"\x00" * 16_002, False),
    ],
)
def test_frame_validation(frame: bytes, valid: bool) -> None:
    assert SessionPolicy.frame_is_valid(frame) is valid


def test_exceeded() -> None:
    policy = SessionPolicy(max_duration_s=10)
    assert not policy.exceeded(9.9)
    assert policy.exceeded(10)
