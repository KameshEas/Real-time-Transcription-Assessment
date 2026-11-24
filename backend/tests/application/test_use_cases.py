from datetime import UTC, datetime, timedelta

import pytest

from hinglish.linguistics.api import tag_words
from hinglish.transcripts.api import (
    AppendFinal,
    CompleteRecording,
    CreateManualTranscript,
    DeleteTranscript,
    EditSegment,
    InvalidValue,
    RenameTranscript,
    RestoreTranscript,
    ResumeRecording,
    SearchQuery,
    StartRecording,
    TranscriptNotFound,
    TranscriptsModule,
    VersionConflict,
    build_transcripts_module,
)
from hinglish.transcripts.application.use_cases import split_into_segments
from hinglish.transcripts.infrastructure.memory import (
    MemoryStore,
    MemoryTranscriptReadModel,
    MemoryUnitOfWork,
)


class StepClock:
    """Each call is one second later, so creation order is deterministic."""

    def __init__(self) -> None:
        self.t = datetime(2026, 11, 24, 9, 0, tzinfo=UTC)

    def now(self) -> datetime:
        self.t += timedelta(seconds=1)
        return self.t


@pytest.fixture
def store() -> MemoryStore:
    return MemoryStore()


@pytest.fixture
def m(store: MemoryStore) -> TranscriptsModule:
    return build_transcripts_module(
        uow=lambda: MemoryUnitOfWork(store),
        read_model=MemoryTranscriptReadModel(store),
        clock=StepClock(),
        tag=tag_words,
    )


async def test_recording_flow_persists_finals_and_completes(m: TranscriptsModule, store: MemoryStore):
    h = await m.start_recording.execute(StartRecording(engine="sarvam", script="mixed", model_id="saaras:v4"))
    s1 = await m.append_final.execute(AppendFinal(h.transcript_id, "आज की meeting", language="hi-IN"))
    s2 = await m.append_final.execute(AppendFinal(h.transcript_id, "budget discuss karenge"))
    await m.complete_recording.execute(CompleteRecording(h.transcript_id, duration_ms=4200))

    d = await m.get.execute(h.transcript_id)
    assert [s1.seq, s2.seq] == [1, 2]
    assert (d.summary.status, d.summary.duration_ms, d.summary.title) == ("completed", 4200, "आज की meeting")
    assert d.summary.hindi_ratio == 0.5  # आज की karenge (hi) vs meeting budget discuss (en)
    assert d.segments[0].words.items[2].lang == "en"
    assert [e.type for e in store.outbox] == [
        "TranscriptCreated",
        "SegmentFinalized",
        "SegmentFinalized",
        "TranscriptCompleted",
    ]


async def test_resume_continues_numbering(m: TranscriptsModule):
    h = await m.start_recording.execute(StartRecording(engine="fake", script="roman"))
    await m.append_final.execute(AppendFinal(h.transcript_id, "pehla"))
    await m.complete_recording.execute(CompleteRecording(h.transcript_id, duration_ms=1000))
    resumed = await m.resume_recording.execute(ResumeRecording(h.transcript_id))
    assert resumed.last_seq == 1
    seg = await m.append_final.execute(AppendFinal(h.transcript_id, "doosra"))
    assert seg.seq == 2


async def test_append_retries_after_a_concurrent_edit(m: TranscriptsModule, store: MemoryStore):
    h = await m.start_recording.execute(StartRecording(engine="fake", script="mixed"))
    real_commit = MemoryUnitOfWork.commit
    calls = {"n": 0}

    async def racing_commit(self: MemoryUnitOfWork) -> None:
        calls["n"] += 1
        if calls["n"] == 1:  # someone renames between our load and our commit
            store.rows[h.transcript_id].version += 1
        await real_commit(self)

    MemoryUnitOfWork.commit = racing_commit  # type: ignore[method-assign]
    try:
        seg = await m.append_final.execute(AppendFinal(h.transcript_id, "still saved"))
    finally:
        MemoryUnitOfWork.commit = real_commit  # type: ignore[method-assign]
    assert seg.seq == 1 and calls["n"] == 2


async def test_manual_note_splits_lines(m: TranscriptsModule):
    d = await m.create_manual.execute(
        CreateManualTranscript(text="pehli line\n\n  doosri   line \n", title=None)
    )
    assert [s.text for s in d.segments] == ["pehli line", "doosri line"]
    assert (d.summary.engine, d.summary.status, d.summary.title) == ("manual", "completed", "pehli line")


async def test_manual_note_rejects_blank_text(m: TranscriptsModule):
    with pytest.raises(InvalidValue):
        await m.create_manual.execute(CreateManualTranscript(text=" \n \n"))


def test_long_lines_split_at_word_boundaries():
    chunks = split_into_segments(("abcd " * 2000).strip())
    assert all(len(c) <= 5000 for c in chunks) and " ".join(chunks) == ("abcd " * 2000).strip()


async def test_rename_requires_current_version(m: TranscriptsModule):
    d = await m.create_manual.execute(CreateManualTranscript(text="hello"))
    v = d.summary.version
    renamed = await m.rename.execute(RenameTranscript(d.summary.id, "Standup notes", expected_version=v))
    assert (renamed.summary.title, renamed.summary.version) == ("Standup notes", v + 1)
    with pytest.raises(VersionConflict):
        await m.rename.execute(RenameTranscript(d.summary.id, "Stale write", expected_version=v))


async def test_edit_segment_recomputes_ratio_and_sets_edited(m: TranscriptsModule):
    d = await m.create_manual.execute(CreateManualTranscript(text="meeting budget"))
    assert d.summary.hindi_ratio == 0.0
    e = await m.edit_segment.execute(EditSegment(d.summary.id, 1, "aaj ki meeting", d.summary.version))
    assert (e.summary.edited, e.summary.hindi_ratio, e.segments[0].text) == (
        True,
        pytest.approx(0.667),
        "aaj ki meeting",
    )


async def test_soft_delete_hides_then_restore_brings_back(m: TranscriptsModule):
    d = await m.create_manual.execute(CreateManualTranscript(text="to delete"))
    await m.delete.execute(DeleteTranscript(d.summary.id))
    with pytest.raises(TranscriptNotFound):
        await m.get.execute(d.summary.id)
    assert (await m.search.execute(SearchQuery())).items == ()
    with pytest.raises(TranscriptNotFound):  # deleted transcripts can't be edited (they're hidden)
        await m.rename.execute(RenameTranscript(d.summary.id, "x", None))
    restored = await m.restore.execute(RestoreTranscript(d.summary.id))
    assert restored.summary.title == "to delete"


async def test_hard_delete_removes_even_soft_deleted(m: TranscriptsModule, store: MemoryStore):
    d = await m.create_manual.execute(CreateManualTranscript(text="gone"))
    await m.delete.execute(DeleteTranscript(d.summary.id))
    await m.delete.execute(DeleteTranscript(d.summary.id, hard=True))
    assert d.summary.id not in store.rows
    with pytest.raises(TranscriptNotFound):
        await m.restore.execute(RestoreTranscript(d.summary.id))
    assert store.outbox[-1].type == "TranscriptDeleted"


async def test_append_to_deleted_recording_fails(m: TranscriptsModule):
    h = await m.start_recording.execute(StartRecording(engine="fake", script="mixed"))
    await m.delete.execute(DeleteTranscript(h.transcript_id))
    with pytest.raises(TranscriptNotFound):
        await m.append_final.execute(AppendFinal(h.transcript_id, "too late"))
    await m.complete_recording.execute(CompleteRecording(h.transcript_id, 10))  # no error: nothing to do


async def test_search_pages_newest_first_and_filters(m: TranscriptsModule):
    for i in range(5):
        await m.create_manual.execute(
            CreateManualTranscript(text=f"note {i} budget" if i % 2 else f"note {i}")
        )
    await m.start_recording.execute(StartRecording(engine="fake", script="mixed"))

    p1 = await m.search.execute(SearchQuery(limit=4))
    p2 = await m.search.execute(SearchQuery(limit=4, cursor=p1.next_cursor))
    assert len(p1.items) == 4 and len(p2.items) == 2 and p2.next_cursor is None
    created = [s.created_at for s in p1.items + p2.items]
    assert created == sorted(created, reverse=True)

    assert {s.title for s in (await m.search.execute(SearchQuery(q="BUDGET"))).items} == {
        "note 1 budget",
        "note 3 budget",
    }
    assert [s.engine for s in (await m.search.execute(SearchQuery(engine="fake"))).items] == ["fake"]


async def test_search_rejects_bad_cursor_and_limit(m: TranscriptsModule):
    with pytest.raises(InvalidValue):
        await m.search.execute(SearchQuery(cursor="not-a-cursor"))
    with pytest.raises(InvalidValue):
        await m.search.execute(SearchQuery(limit=0))


async def test_export_has_header_and_one_line_per_segment(m: TranscriptsModule):
    d = await m.create_manual.execute(
        CreateManualTranscript(text="aaj ki meeting\nbudget", title="Team Sync!")
    )
    name, text = await m.export.execute(d.summary.id)
    assert name == "team-sync.txt"
    assert text.splitlines()[0] == "Team Sync!"
    assert text.endswith("aaj ki meeting\nbudget\n")


async def test_restore_is_idempotent(m: TranscriptsModule):
    d = await m.create_manual.execute(CreateManualTranscript(text="x"))
    await m.delete.execute(DeleteTranscript(d.summary.id))
    await m.restore.execute(RestoreTranscript(d.summary.id))
    again = await m.restore.execute(RestoreTranscript(d.summary.id))
    assert again.summary.title == "x"
