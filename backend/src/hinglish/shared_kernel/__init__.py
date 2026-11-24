"""Shared kernel: primitives every bounded context may depend on. Standard library only."""

from hinglish.shared_kernel.base import DomainError, DomainEvent, Entity, ValueObject
from hinglish.shared_kernel.ids import TenantId, new_id
from hinglish.shared_kernel.time import Clock, SystemClock

__all__ = [
    "Clock",
    "DomainError",
    "DomainEvent",
    "Entity",
    "SystemClock",
    "TenantId",
    "ValueObject",
    "new_id",
]
