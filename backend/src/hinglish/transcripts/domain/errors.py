from __future__ import annotations

from hinglish.shared_kernel import DomainError


class InvalidValue(DomainError):
    code = "INVALID_VALUE"

    def __init__(self, message: str, *, field: str) -> None:
        super().__init__(message)
        self.field = field


class TranscriptNotFound(DomainError):
    code = "TRANSCRIPT_NOT_FOUND"


class TranscriptIsDeleted(DomainError):
    code = "TRANSCRIPT_DELETED"


class SegmentNotFound(DomainError):
    code = "SEGMENT_NOT_FOUND"


class VersionConflict(DomainError):
    code = "VERSION_CONFLICT"


class InvalidStateTransition(DomainError):
    code = "INVALID_STATE"
