"""Public facade of the Transcripts context. Other contexts (and the composition root) import only this.

`TranscriptsModule` bundles the use cases; build it with `build_transcripts_module` from the ports.
"""

from __future__ import annotations

from dataclasses import dataclass

from hinglish.shared_kernel import Clock
from hinglish.transcripts.application.dto import (
    Page,
    RecordingHandle,
    SearchQuery,
    SegmentView,
    TranscriptDetail,
    TranscriptSummary,
)
from hinglish.transcripts.application.ports import Tagger, TranscriptReadModel, UnitOfWorkFactory
from hinglish.transcripts.application.use_cases import (
    AppendFinal,
    AppendFinalHandler,
    CompleteRecording,
    CompleteRecordingHandler,
    CreateManualTranscript,
    CreateManualTranscriptHandler,
    DeleteTranscript,
    DeleteTranscriptHandler,
    Deps,
    EditSegment,
    EditSegmentHandler,
    ExportTranscript,
    GetTranscript,
    RenameTranscript,
    RenameTranscriptHandler,
    RestoreTranscript,
    RestoreTranscriptHandler,
    ResumeRecording,
    ResumeRecordingHandler,
    SearchTranscripts,
    StartRecording,
    StartRecordingHandler,
)
from hinglish.transcripts.domain.errors import (
    InvalidStateTransition,
    InvalidValue,
    SegmentNotFound,
    TranscriptIsDeleted,
    TranscriptNotFound,
    VersionConflict,
)


@dataclass(frozen=True)
class TranscriptsModule:
    start_recording: StartRecordingHandler
    resume_recording: ResumeRecordingHandler
    append_final: AppendFinalHandler
    complete_recording: CompleteRecordingHandler
    create_manual: CreateManualTranscriptHandler
    rename: RenameTranscriptHandler
    edit_segment: EditSegmentHandler
    delete: DeleteTranscriptHandler
    restore: RestoreTranscriptHandler
    search: SearchTranscripts
    get: GetTranscript
    export: ExportTranscript


def build_transcripts_module(
    *, uow: UnitOfWorkFactory, read_model: TranscriptReadModel, clock: Clock, tag: Tagger
) -> TranscriptsModule:
    deps = Deps(uow=uow, clock=clock, tag=tag)
    return TranscriptsModule(
        start_recording=StartRecordingHandler(deps),
        resume_recording=ResumeRecordingHandler(deps),
        append_final=AppendFinalHandler(deps),
        complete_recording=CompleteRecordingHandler(deps),
        create_manual=CreateManualTranscriptHandler(deps),
        rename=RenameTranscriptHandler(deps),
        edit_segment=EditSegmentHandler(deps),
        delete=DeleteTranscriptHandler(deps),
        restore=RestoreTranscriptHandler(deps),
        search=SearchTranscripts(read_model),
        get=GetTranscript(read_model),
        export=ExportTranscript(read_model),
    )


__all__ = [
    "AppendFinal",
    "CompleteRecording",
    "CreateManualTranscript",
    "DeleteTranscript",
    "EditSegment",
    "InvalidStateTransition",
    "InvalidValue",
    "Page",
    "RecordingHandle",
    "RenameTranscript",
    "RestoreTranscript",
    "ResumeRecording",
    "SearchQuery",
    "SegmentNotFound",
    "SegmentView",
    "StartRecording",
    "TranscriptDetail",
    "TranscriptIsDeleted",
    "TranscriptNotFound",
    "TranscriptSummary",
    "TranscriptsModule",
    "VersionConflict",
    "build_transcripts_module",
]
