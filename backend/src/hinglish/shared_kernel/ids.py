from __future__ import annotations

from typing import NewType
from uuid import UUID, uuid4

TenantId = NewType("TenantId", str)
PUBLIC_TENANT = TenantId("public")


def new_id() -> UUID:
    return uuid4()
