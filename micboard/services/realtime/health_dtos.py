"""Typed outcomes for real-time connection health maintenance."""

from __future__ import annotations

from pydantic import Field

from micboard.services.shared.base_dto import PydanticBaseDTO


class RealtimeConnectionHealthResult(PydanticBaseDTO):
    """Bounded result of one stale-connection maintenance sweep."""

    stale_disconnected: int = Field(default=0, ge=0)
    errors_reset: int = Field(default=0, ge=0)
    active: int = Field(default=0, ge=0)
    errors: int = Field(default=0, ge=0)
    stale_truncated: bool = False
    error_truncated: bool = False
    failed: bool = False
    error_type: str | None = None


class RealtimeConnectionStatusSummary(PydanticBaseDTO):
    """Secret-safe aggregate of persisted real-time connection states."""

    total: int = Field(default=0, ge=0)
    connected: int = Field(default=0, ge=0)
    connecting: int = Field(default=0, ge=0)
    disconnected: int = Field(default=0, ge=0)
    error: int = Field(default=0, ge=0)
    stopped: int = Field(default=0, ge=0)
    healthy_percentage: float = Field(default=0.0, ge=0.0, le=100.0)
    failed: bool = False
    error_type: str | None = None
