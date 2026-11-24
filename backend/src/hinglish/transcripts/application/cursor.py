"""Opaque keyset cursor for `ORDER BY created_at DESC, id DESC` pagination."""

from __future__ import annotations

import base64
import binascii
import json
from datetime import datetime
from uuid import UUID

from hinglish.transcripts.domain.errors import InvalidValue


def encode_cursor(created_at: datetime, id: UUID) -> str:
    raw = json.dumps([created_at.isoformat(), str(id)]).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        created_at, id = json.loads(base64.urlsafe_b64decode(padded))
        return datetime.fromisoformat(created_at), UUID(id)
    except (ValueError, TypeError, binascii.Error) as exc:
        raise InvalidValue("Invalid cursor.", field="cursor") from exc
