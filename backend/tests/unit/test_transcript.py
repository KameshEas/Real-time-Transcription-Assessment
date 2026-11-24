from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from hinglish.linguistics.api import tag_words
from hinglish.shared_kernel import TenantId
from hinglish.transcripts.domain.errors import (
    InvalidStateTransition,
    InvalidValue,
    SegmentNotFound,
    TranscriptIsDeleted,
)
from hinglish.transcripts.domain.transcript import DEFAULT_TITLE, Transcript
from hinglish.transcripts.domain.value_objects import (
    Engine,
    ScriptMode,
    SegmentText,
    Title,
    TranscriptStatus,
)

T0 = datetime(2026, 11, 24, 10, 0, tzinfo=UTC)


def recording() -> Transcript:
    return Transcript.start_recording(
        id=uuid4(), tenant_id=TenantId("public"), engine=Engine.SARVAM, script_mode=ScriptMode.MIXED, now=T0
    )


def append(t: Transcript, text: str):
    return t.append_segment(SegmentText(text), tag_words(text), now=T0)


def event_types(t: Transcript) -> list[str]:
    return [e.type for e in t.pull_events()]


def test_recording_appends_with_increasing_seq_and_auto_title():
    t = recording()
    assert t.state.title == DEFAULT_TITLE
    assert append(t, "aaj ki meeting").seq == 1
    assert append(t, "budget discuss karenge").seq == 2
    assert t.state.title == "aaj ki meeting"
    assert t.full_text == "aaj ki meeting\nbudget discuss karenge"
    assert t.version == 3
    assert event_types(t) == ["TranscriptCreated", "SegmentFinalized", "SegmentFinalized"]


def test_long_first_segment_gives_truncated_title():
    t = recording()
    append(t, "word " * 30)
    assert t.state.title.endswith("…") and len(t.state.title) <= 61


def test_hindi_ratio_tracks_segments():
    t = recording()
    append(t, "aaj ki meeting")  # hi hi en
    assert t.hindi_ratio == pytest.approx(0.667)


def test_complete_is_idempotent_and_accumulates_duration_across_resume():
    t = recording()
    t.complete(now=T0, duration_ms=1000)
    t.complete(now=T0, duration_ms=5000)  # stop racing a disconnect: ignored
    assert (t.state.status, t.state.duration_ms) == (TranscriptStatus.COMPLETED, 1000)
    t.reopen_for_recording(now=T0)
    append(t, "phir se")
    t.complete(now=T0, duration_ms=500)
    assert t.state.duration_ms == 1500
    assert t.last_seq == 1


def test_cannot_append_after_completion():
    t = recording()
    t.complete(now=T0, duration_ms=None)
    with pytest.raises(InvalidStateTransition):
        append(t, "late final")


def test_manual_note_is_completed_and_cannot_be_resumed():
    t = Transcript.create_manual(
        id=uuid4(),
        tenant_id=TenantId("public"),
        title=None,
        segments=[(SegmentText("first line"), tag_words("first line"))],
        now=T0,
    )
    assert (t.state.engine, t.state.status, t.state.title) == (
        Engine.MANUAL,
        TranscriptStatus.COMPLETED,
        "first line",
    )
    with pytest.raises(InvalidStateTransition):
        t.reopen_for_recording(now=T0)


def test_edit_segment_marks_edited_and_clears_conversions():
    t = recording()
    seg = append(t, "aaj meeting")
    seg.text_deva = "आज meeting"
    t.pull_dirty_segments()
    t.edit_segment(1, SegmentText("kal meeting"), tag_words("kal meeting"), now=T0 + timedelta(seconds=1))
    assert (seg.text, seg.text_deva, t.state.edited) == ("kal meeting", None, True)
    assert [s.seq for s in t.pull_dirty_segments()] == [1]


def test_unchanged_edits_do_not_bump_version():
    t = recording()
    append(t, "same")
    t.rename(Title("Standup"), now=T0)
    v = t.version
    t.rename(Title("  Standup "), now=T0)
    t.edit_segment(1, SegmentText("same"), tag_words("same"), now=T0)
    assert t.version == v


def test_edit_unknown_segment():
    with pytest.raises(SegmentNotFound):
        recording().edit_segment(9, SegmentText("x"), tag_words("x"), now=T0)


def test_deleted_transcript_rejects_changes_until_restored():
    t = recording()
    t.soft_delete(now=T0)
    with pytest.raises(TranscriptIsDeleted):
        t.rename(Title("x"), now=T0)
    t.restore(now=T0)
    t.rename(Title("x"), now=T0)
    assert t.state.title == "x"


@pytest.mark.parametrize("bad", ["", "   ", "x" * 201])
def test_title_validation(bad: str):
    with pytest.raises(InvalidValue):
        Title(bad)


def test_title_collapses_whitespace():
    assert Title("  Team   sync \n").value == "Team sync"


@pytest.mark.parametrize("bad", ["", "  ", "x" * 5001])
def test_segment_text_validation(bad: str):
    with pytest.raises(InvalidValue):
        SegmentText(bad)
