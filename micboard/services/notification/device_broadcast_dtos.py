"""Typed results for bounded, resumable device broadcasts."""

from __future__ import annotations

from pydantic import Field

from micboard.services.shared.base_dto import PydanticBaseDTO

MAX_DEVICE_BROADCAST_ROWS = 5_000


class DeviceBroadcastCursor(PydanticBaseDTO):
    """Cache-safe continuation state for one manufacturer projection."""

    after_id: int = Field(default=0, ge=0)
    snapshot_id: str = Field(default="", max_length=64)


class DeviceBroadcastResult(PydanticBaseDTO):
    """Bounded outcome of one projection broadcast batch."""

    rows_sent: int = Field(ge=0, le=MAX_DEVICE_BROADCAST_ROWS)
    chunks_sent: int = Field(ge=1, le=MAX_DEVICE_BROADCAST_ROWS)
    inventory_complete: bool
    next_cursor: int = Field(ge=0)
